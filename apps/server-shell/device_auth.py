"""Ed25519 device authentication and server-issued local certificates.

This is server-owned operational security. It never writes Memoria.ia semantic
state and never accesses BDR internals.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
from threading import RLock
import time
from typing import Any
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from device_registry import AuditLog, DeviceRegistry, DeviceRegistryError, ServerIdentity, _atomic_json

AUTH_PREFIX = "/api/server/v1/device-auth"
DEVICE_HEARTBEAT_PATH = "/api/server/v1/device/heartbeat"
DEVICE_SELF_PATH = "/api/server/v1/device/self"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    text = value.strip()
    padding = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode((text + padding).encode("ascii"))
    except Exception as exc:
        raise DeviceRegistryError(422, "invalid_base64", "invalid base64url value") from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: object) -> datetime | None:
    try:
        text = str(value)
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def parse_ed25519_public_key(value: str) -> Ed25519PublicKey:
    text = value.strip()
    if text.startswith("ed25519:"):
        raw = _b64decode(text.split(":", 1)[1])
        if len(raw) != 32:
            raise DeviceRegistryError(422, "invalid_ed25519_key", "Ed25519 raw public key must be 32 bytes")
        return Ed25519PublicKey.from_public_bytes(raw)
    if "BEGIN PUBLIC KEY" in text:
        try:
            key = serialization.load_pem_public_key(text.encode("utf-8"))
        except Exception as exc:
            raise DeviceRegistryError(422, "invalid_ed25519_key", "invalid PEM public key") from exc
        if not isinstance(key, Ed25519PublicKey):
            raise DeviceRegistryError(422, "invalid_ed25519_key", "public key is not Ed25519")
        return key
    raise DeviceRegistryError(422, "invalid_ed25519_key", "public key must use ed25519:<base64url> or PEM")


class DeviceAuthority:
    SCHEMA = "memoria-server-device-authority/v1"
    CERT_SCHEMA = "memoria-server-device-certificate/v1"

    def __init__(self, data_dir: str | Path, identity: ServerIdentity, audit: AuditLog) -> None:
        self.root = Path(data_dir)
        self.path = self.root / "device-authority.json"
        self.identity = identity
        self.audit = audit
        self._lock = RLock()
        self._private_key, self._public_text, self._created_at = self._load_or_create()

    def _load_or_create(self) -> tuple[Ed25519PrivateKey, str, str]:
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text("utf-8"))
                if payload.get("schema") != self.SCHEMA or payload.get("server_id") != self.identity.snapshot()["server_id"]:
                    raise RuntimeError("device authority state does not match server identity")
                raw = _b64decode(str(payload.get("private_key") or ""))
                if len(raw) != 32:
                    raise RuntimeError("device authority private key has invalid size")
                key = Ed25519PrivateKey.from_private_bytes(raw)
                public_text = "ed25519:" + _b64encode(
                    key.public_key().public_bytes(
                        encoding=serialization.Encoding.Raw,
                        format=serialization.PublicFormat.Raw,
                    )
                )
                if payload.get("public_key") and payload.get("public_key") != public_text:
                    raise RuntimeError("device authority public/private key mismatch")
                return key, public_text, str(payload.get("created_at") or _now())
            except DeviceRegistryError as exc:
                raise RuntimeError("device authority state is invalid") from exc
            except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
                raise RuntimeError("device authority state is unreadable") from exc

        key = Ed25519PrivateKey.generate()
        private_raw = key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_raw = key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        created_at = _now()
        payload = {
            "schema": self.SCHEMA,
            "server_id": self.identity.snapshot()["server_id"],
            "algorithm": "Ed25519",
            "private_key": _b64encode(private_raw),
            "public_key": "ed25519:" + _b64encode(public_raw),
            "created_at": created_at,
        }
        _atomic_json(self.path, payload, mode=0o600)
        return key, str(payload["public_key"]), created_at

    def public_snapshot(self) -> dict[str, object]:
        return {
            "schema": self.SCHEMA,
            "server_id": self.identity.snapshot()["server_id"],
            "algorithm": "Ed25519",
            "public_key": self._public_text,
            "public_key_fingerprint": "sha256:" + hashlib.sha256(self._public_text.encode("utf-8")).hexdigest(),
            "created_at": self._created_at,
        }

    @staticmethod
    def _certificate_valid(certificate: object, fingerprint: str, server_id: str) -> bool:
        if not isinstance(certificate, dict):
            return False
        payload = certificate.get("payload")
        if not isinstance(payload, dict):
            return False
        expires = _parse_time(payload.get("valid_until"))
        return bool(
            certificate.get("schema") == DeviceAuthority.CERT_SCHEMA
            and payload.get("server_id") == server_id
            and payload.get("device_id")
            and payload.get("public_key_fingerprint") == fingerprint
            and expires
            and expires > datetime.now(timezone.utc)
        )

    def issue_certificate(self, device: dict[str, object]) -> dict[str, object] | None:
        public_key = str(device.get("public_key") or "")
        try:
            parse_ed25519_public_key(public_key)
        except DeviceRegistryError:
            return None

        server_id = str(self.identity.snapshot()["server_id"])
        fingerprint = str(device.get("public_key_fingerprint") or "")
        existing = device.get("certificate")
        if self._certificate_valid(existing, fingerprint, server_id):
            existing_payload = existing.get("payload") if isinstance(existing, dict) else None
            if isinstance(existing_payload, dict) and existing_payload.get("device_id") == device.get("device_id"):
                return dict(existing)

        issued = datetime.now(timezone.utc)
        payload = {
            "schema": self.CERT_SCHEMA,
            "serial": "cert-" + uuid4().hex,
            "server_id": server_id,
            "device_id": str(device.get("device_id") or ""),
            "public_key_fingerprint": fingerprint,
            "permissions": list(device.get("permissions") or []),
            "issued_at": issued.isoformat(),
            "valid_until": (issued + timedelta(days=365)).isoformat(),
        }
        signature = _b64encode(self._private_key.sign(_canonical(payload)))
        certificate = {
            "schema": self.CERT_SCHEMA,
            "algorithm": "Ed25519",
            "issuer_public_key": self._public_text,
            "payload": payload,
            "signature": signature,
        }
        self.audit.append(
            "device.certificate_issued",
            actor="server-authority",
            target=str(device.get("device_id") or ""),
            details={"serial": payload["serial"], "valid_until": payload["valid_until"]},
        )
        return certificate

    def verify_certificate(self, certificate: dict[str, object]) -> bool:
        try:
            if certificate.get("schema") != self.CERT_SCHEMA or certificate.get("algorithm") != "Ed25519":
                return False
            if certificate.get("issuer_public_key") != self._public_text:
                return False
            payload = certificate.get("payload")
            if not isinstance(payload, dict) or payload.get("server_id") != self.identity.snapshot()["server_id"]:
                return False
            signature = _b64decode(str(certificate.get("signature") or ""))
            self._private_key.public_key().verify(signature, _canonical(payload))
            expires = _parse_time(payload.get("valid_until"))
            return bool(expires and expires > datetime.now(timezone.utc))
        except (InvalidSignature, DeviceRegistryError, ValueError, TypeError):
            return False


    def verify_device_certificate(self, certificate: object, device: dict[str, object]) -> bool:
        if not isinstance(certificate, dict) or not self.verify_certificate(certificate):
            return False
        payload = certificate.get("payload")
        return bool(
            isinstance(payload, dict)
            and payload.get("device_id") == device.get("device_id")
            and payload.get("public_key_fingerprint") == device.get("public_key_fingerprint")
            and payload.get("server_id") == self.identity.snapshot()["server_id"]
        )

class DeviceAuthManager:
    CHALLENGE_SCHEMA = "memoria-server-device-challenge/v1"
    TOKEN_SCHEMA = "memoria-server-device-token/v1"

    def __init__(
        self,
        registry: DeviceRegistry,
        authority: DeviceAuthority,
        audit: AuditLog,
        *,
        challenge_seconds: int = 60,
        token_seconds: int = 3600,
    ) -> None:
        self.registry = registry
        self.authority = authority
        self.audit = audit
        self.challenge_seconds = max(10, int(challenge_seconds))
        self.token_seconds = max(60, int(token_seconds))
        self._lock = RLock()
        self._challenges: dict[str, dict[str, object]] = {}
        self._tokens: dict[str, dict[str, object]] = {}

    def _cleanup(self) -> None:
        now = time.monotonic()
        self._challenges = {key: value for key, value in self._challenges.items() if float(value["expires_mono"]) > now}
        self._tokens = {key: value for key, value in self._tokens.items() if float(value["expires_mono"]) > now}

    @staticmethod
    def _message(server_id: str, device_id: str, challenge_id: str, nonce: str) -> bytes:
        return (
            "memoria-server-device-auth/v1\n"
            + server_id + "\n"
            + device_id + "\n"
            + challenge_id + "\n"
            + nonce
        ).encode("utf-8")

    def challenge(self, device_id: str, *, client_ip: str | None = None) -> dict[str, object]:
        device = self.registry.get(device_id)
        if device.get("status") != "active":
            raise DeviceRegistryError(403, "device_not_active", "device must be active")
        certificate = device.get("certificate")
        if device.get("certificate_status") != "active" or not self.authority.verify_device_certificate(certificate, device):
            raise DeviceRegistryError(403, "certificate_not_active", "device does not have an active server certificate")
        challenge_id = "chl-" + uuid4().hex
        nonce = _b64encode(secrets.token_bytes(32))
        server_id = str(self.authority.identity.snapshot()["server_id"])
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.challenge_seconds)
        with self._lock:
            self._cleanup()
            # Keep a bounded number of outstanding challenges for each device.
            outstanding = [key for key, item in self._challenges.items() if item.get("device_id") == device_id]
            for key in outstanding[:-4]:
                self._challenges.pop(key, None)
            self._challenges[challenge_id] = {
                "device_id": device_id,
                "nonce": nonce,
                "server_id": server_id,
                "expires_mono": time.monotonic() + self.challenge_seconds,
                "client_ip": client_ip,
            }
        self.audit.append("device.auth_challenge", actor=f"device:{device_id}", target=device_id, client_ip=client_ip)
        return {
            "schema": self.CHALLENGE_SCHEMA,
            "challenge_id": challenge_id,
            "server_id": server_id,
            "device_id": device_id,
            "nonce": nonce,
            "expires_at": expires_at.isoformat(),
            "certificate": certificate,
            "signing_message": self._message(server_id, device_id, challenge_id, nonce).decode("utf-8"),
        }

    def verify(
        self,
        device_id: str,
        challenge_id: str,
        signature_text: str,
        *,
        client_ip: str | None = None,
    ) -> dict[str, object]:
        with self._lock:
            self._cleanup()
            challenge = self._challenges.pop(challenge_id, None)
        if not challenge or challenge.get("device_id") != device_id:
            self.audit.append("device.auth_failed", actor=f"device:{device_id}", target=device_id, client_ip=client_ip, details={"reason":"challenge_invalid"})
            raise DeviceRegistryError(401, "challenge_invalid", "challenge is invalid, expired or already used")

        device = self.registry.get(device_id)
        if device.get("status") != "active":
            raise DeviceRegistryError(403, "device_not_active", "device must be active")
        certificate = device.get("certificate")
        if device.get("certificate_status") != "active" or not self.authority.verify_device_certificate(certificate, device):
            raise DeviceRegistryError(403, "certificate_not_active", "device certificate is not active")

        public_key = parse_ed25519_public_key(str(device.get("public_key") or ""))
        signature = _b64decode(signature_text)
        message = self._message(
            str(challenge["server_id"]),
            device_id,
            challenge_id,
            str(challenge["nonce"]),
        )
        try:
            public_key.verify(signature, message)
        except InvalidSignature as exc:
            self.audit.append("device.auth_failed", actor=f"device:{device_id}", target=device_id, client_ip=client_ip, details={"reason":"signature_invalid"})
            raise DeviceRegistryError(401, "signature_invalid", "device signature is invalid") from exc

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._lock:
            self._cleanup()
            same_device = [
                (key, value) for key, value in self._tokens.items()
                if value.get("device_id") == device_id
            ]
            same_device.sort(key=lambda pair: float(pair[1].get("issued_mono") or 0.0))
            for key, _value in same_device[:-3]:
                self._tokens.pop(key, None)
            self._tokens[token_hash] = {
                "device_id": device_id,
                "expires_mono": time.monotonic() + self.token_seconds,
                "issued_mono": time.monotonic(),
                "issued_at": _now(),
            }
        self.audit.append("device.auth_success", actor=f"device:{device_id}", target=device_id, client_ip=client_ip)
        return {
            "schema": self.TOKEN_SCHEMA,
            "token": token,
            "token_type": "Device",
            "expires_in": self.token_seconds,
            "device_id": device_id,
        }

    def authenticate(self, authorization: str) -> str:
        prefix = "Device "
        if not authorization.startswith(prefix):
            raise DeviceRegistryError(401, "device_auth_required", "Device authorization token required")
        token = authorization[len(prefix):].strip()
        if not token:
            raise DeviceRegistryError(401, "device_auth_required", "Device authorization token required")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._lock:
            self._cleanup()
            item = self._tokens.get(token_hash)
        if not item:
            raise DeviceRegistryError(401, "device_token_invalid", "device token is invalid or expired")
        device_id = str(item["device_id"])
        device = self.registry.get(device_id)
        if device.get("status") != "active" or device.get("certificate_status") != "active":
            raise DeviceRegistryError(403, "device_not_active", "device is not active")
        return device_id

    @staticmethod
    def _json_body(handler) -> dict[str, object]:
        body = handler._read_body()
        if body is None:
            raise DeviceRegistryError(400, "invalid_body", "request body could not be read")
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeviceRegistryError(400, "invalid_json", "JSON object required") from exc
        if not isinstance(payload, dict):
            raise DeviceRegistryError(400, "invalid_json", "JSON object required")
        return payload

    def dispatch_public(self, handler, path: str) -> bool:
        if path != AUTH_PREFIX and not path.startswith(AUTH_PREFIX + "/"):
            return False
        suffix = path[len(AUTH_PREFIX):].strip("/")
        client_ip = handler.client_address[0] if getattr(handler, "client_address", None) else None
        try:
            if suffix == "authority" and handler.command in {"GET", "HEAD"}:
                handler._write_json(200, self.authority.public_snapshot())
                return True
            if suffix == "challenge" and handler.command == "POST":
                payload = self._json_body(handler)
                handler._write_json(200, self.challenge(str(payload.get("device_id") or ""), client_ip=client_ip))
                return True
            if suffix == "verify" and handler.command == "POST":
                payload = self._json_body(handler)
                handler._write_json(
                    200,
                    self.verify(
                        str(payload.get("device_id") or ""),
                        str(payload.get("challenge_id") or ""),
                        str(payload.get("signature") or ""),
                        client_ip=client_ip,
                    ),
                )
                return True
            handler._write_json(405 if suffix in {"authority","challenge","verify"} else 404, {"error":"method_not_allowed" if suffix in {"authority","challenge","verify"} else "route_not_found"})
            return True
        except DeviceRegistryError as exc:
            handler._write_json(exc.status, {"error": exc.code, "detail": exc.detail})
            return True

    def dispatch_device(self, handler, path: str) -> bool:
        if path not in {DEVICE_HEARTBEAT_PATH, DEVICE_SELF_PATH}:
            return False
        client_ip = handler.client_address[0] if getattr(handler, "client_address", None) else None
        try:
            device_id = self.authenticate(handler.headers.get("Authorization", ""))
            if path == DEVICE_SELF_PATH:
                if handler.command not in {"GET", "HEAD"}:
                    handler._write_json(405, {"error":"method_not_allowed"}, {"Allow":"GET, HEAD"})
                else:
                    handler._write_json(200, self.registry.get(device_id))
                return True
            if handler.command != "POST":
                handler._write_json(405, {"error":"method_not_allowed"}, {"Allow":"POST"})
                return True
            payload = self._json_body(handler)
            result = self.registry.heartbeat(
                device_id,
                payload,
                actor=f"device:{device_id}",
                client_ip=client_ip,
            )
            handler._write_json(200, result)
            return True
        except DeviceRegistryError as exc:
            handler._write_json(exc.status, {"error":exc.code, "detail":exc.detail})
            return True
