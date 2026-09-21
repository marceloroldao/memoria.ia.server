"""Server-owned one-time enrollment invitations for devices.

Enrollment is operational metadata only. Invitation secrets are never persisted
in plaintext; the claim code is returned once to the administrator and the
server stores only its SHA-256 digest.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
from threading import RLock
import time
from typing import Any
from uuid import uuid4

from device_auth import parse_ed25519_public_key
from device_registry import (
    AuditLog,
    DeviceRegistry,
    DeviceRegistryError,
    ServerIdentity,
    _atomic_json,
    normalize_device_permissions,
)

ADMIN_PREFIX = "/api/server/v1/enrollments"
PUBLIC_CLAIM_PATH = "/api/server/v1/device-enrollment/claim"
_ALLOWED_DEVICE_TYPES = {"offia", "phone", "computer", "server", "robot", "sensor", "iot"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse_time(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _code_digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


class DeviceEnrollmentManager:
    SCHEMA = "memoria-server-device-enrollments/v1"
    INVITE_SCHEMA = "memoria-server-device-enrollment/v1"

    def __init__(
        self,
        data_dir: str | Path,
        identity: ServerIdentity,
        registry: DeviceRegistry,
        audit: AuditLog,
    ) -> None:
        self.root = Path(data_dir)
        self.path = self.root / "enrollments.json"
        self.identity = identity
        self.registry = registry
        self.audit = audit
        self._lock = RLock()
        self._claim_rate: dict[str, deque[float]] = defaultdict(deque)
        self.root.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema": self.SCHEMA, "updated_at": _iso(_now()), "invitations": {}}
        try:
            payload = json.loads(self.path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("device enrollment state is unreadable") from exc
        if (
            isinstance(payload, dict)
            and payload.get("schema") == self.SCHEMA
            and isinstance(payload.get("invitations"), dict)
        ):
            return payload
        raise RuntimeError("device enrollment state is invalid")

    def _save(self) -> None:
        self._state["updated_at"] = _iso(_now())
        _atomic_json(self.path, self._state)

    def _refresh_expired_locked(self) -> bool:
        changed = False
        now = _now()
        invitations = self._state.get("invitations")
        if not isinstance(invitations, dict):
            return False
        for invitation in invitations.values():
            if not isinstance(invitation, dict) or invitation.get("status") != "active":
                continue
            expires = _parse_time(invitation.get("expires_at"))
            if expires is None or expires <= now:
                invitation["status"] = "expired"
                invitation["updated_at"] = _iso(now)
                changed = True
        return changed

    @staticmethod
    def _public(invitation: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in invitation.items()
            if key not in {"code_hash", "claim_started_at"}
        }

    def create(
        self,
        payload: dict[str, object],
        *,
        actor: str,
        client_ip: str | None = None,
    ) -> dict[str, object]:
        label = str(payload.get("label") or "Novo dispositivo").strip()[:160] or "Novo dispositivo"
        device_type = str(payload.get("type") or "offia").strip().casefold()
        if device_type not in _ALLOWED_DEVICE_TYPES:
            raise DeviceRegistryError(422, "invalid_type", "unsupported device type")
        permissions = normalize_device_permissions(payload.get("permissions"), default_if_empty=True)
        groups_raw = payload.get("groups") or []
        if not isinstance(groups_raw, list):
            raise DeviceRegistryError(422, "invalid_groups", "groups must be a JSON list")
        groups = []
        for value in groups_raw[:32]:
            item = str(value).strip()[:128]
            if item and item not in groups:
                groups.append(item)
        try:
            expires_minutes = int(payload.get("expires_minutes") or 60)
        except (TypeError, ValueError) as exc:
            raise DeviceRegistryError(422, "invalid_expiration", "expires_minutes must be an integer") from exc
        expires_minutes = max(5, min(expires_minutes, 7 * 24 * 60))

        now = _now()
        enrollment_id = "enr-" + uuid4().hex
        code = "enr1_" + secrets.token_urlsafe(24)
        invitation: dict[str, Any] = {
            "schema": self.INVITE_SCHEMA,
            "enrollment_id": enrollment_id,
            "server_id": self.identity.snapshot()["server_id"],
            "label": label,
            "type": device_type,
            "permissions": permissions,
            "groups": groups,
            "status": "active",
            "code_hash": _code_digest(code),
            "created_at": _iso(now),
            "updated_at": _iso(now),
            "expires_at": _iso(now + timedelta(minutes=expires_minutes)),
            "claimed_at": None,
            "device_id": None,
        }

        with self._lock:
            self._refresh_expired_locked()
            invitations = self._state["invitations"]
            assert isinstance(invitations, dict)
            invitations[enrollment_id] = invitation
            self._save()

        self.audit.append(
            "enrollment.created",
            actor=actor,
            target=enrollment_id,
            client_ip=client_ip,
            details={
                "label": label,
                "type": device_type,
                "permissions": permissions,
                "expires_at": invitation["expires_at"],
            },
        )
        return {
            "schema": self.INVITE_SCHEMA,
            "enrollment_code": code,
            "invitation": self._public(invitation),
        }

    def list(self) -> dict[str, object]:
        with self._lock:
            changed = self._refresh_expired_locked()
            if changed:
                self._save()
            invitations = self._state.get("invitations")
            rows = [
                self._public(dict(value))
                for value in (invitations or {}).values()
                if isinstance(value, dict)
            ] if isinstance(invitations, dict) else []
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return {"schema": self.SCHEMA, "count": len(rows), "invitations": rows}

    def revoke(
        self,
        enrollment_id: str,
        *,
        actor: str,
        client_ip: str | None = None,
    ) -> dict[str, object]:
        with self._lock:
            invitations = self._state.get("invitations")
            invitation = invitations.get(enrollment_id) if isinstance(invitations, dict) else None
            if not isinstance(invitation, dict):
                raise DeviceRegistryError(404, "enrollment_not_found", "enrollment invitation not found")
            if invitation.get("status") == "consumed":
                raise DeviceRegistryError(409, "enrollment_consumed", "consumed enrollment cannot be revoked")
            if invitation.get("status") == "revoked":
                return self._public(dict(invitation))
            invitation["status"] = "revoked"
            invitation["updated_at"] = _iso(_now())
            self._save()
            result = self._public(dict(invitation))

        self.audit.append(
            "enrollment.revoked",
            actor=actor,
            target=enrollment_id,
            client_ip=client_ip,
        )
        return result

    def _check_rate(self, client_ip: str | None) -> None:
        key = client_ip or "unknown"
        now = time.monotonic()
        with self._lock:
            for ip in list(self._claim_rate):
                attempts = self._claim_rate[ip]
                while attempts and now - attempts[0] > 60.0:
                    attempts.popleft()
                if not attempts:
                    self._claim_rate.pop(ip, None)
            attempts = self._claim_rate[key]
            if len(attempts) >= 20:
                raise DeviceRegistryError(429, "enrollment_rate_limited", "too many enrollment attempts")
            attempts.append(now)

    def claim(
        self,
        payload: dict[str, object],
        *,
        client_ip: str | None = None,
    ) -> dict[str, object]:
        self._check_rate(client_ip)
        code = str(payload.get("enrollment_code") or "").strip()
        if len(code) < 24 or len(code) > 256:
            raise DeviceRegistryError(401, "enrollment_code_invalid", "enrollment code is invalid")
        name = str(payload.get("name") or "").strip()
        if not name:
            raise DeviceRegistryError(422, "invalid_name", "device name is required")
        public_key = str(payload.get("public_key") or "").strip()
        # Enrollment V1 is the secure path: only Ed25519 keys are accepted.
        parse_ed25519_public_key(public_key)

        digest = _code_digest(code)
        invitation: dict[str, Any] | None = None
        enrollment_id = ""
        now = _now()

        with self._lock:
            changed = self._refresh_expired_locked()
            invitations = self._state.get("invitations")
            if isinstance(invitations, dict):
                for candidate_id, candidate in invitations.items():
                    if not isinstance(candidate, dict):
                        continue
                    stored = str(candidate.get("code_hash") or "")
                    if stored and hmac.compare_digest(stored, digest):
                        enrollment_id = str(candidate_id)
                        invitation = candidate
                        break
            if invitation is None:
                if changed:
                    self._save()
                raise DeviceRegistryError(401, "enrollment_code_invalid", "enrollment code is invalid")
            status = str(invitation.get("status") or "")
            if status == "expired":
                if changed:
                    self._save()
                raise DeviceRegistryError(410, "enrollment_expired", "enrollment invitation expired")
            if status == "revoked":
                raise DeviceRegistryError(403, "enrollment_revoked", "enrollment invitation was revoked")
            if status == "consumed":
                raise DeviceRegistryError(409, "enrollment_consumed", "enrollment invitation was already used")
            if status != "active":
                raise DeviceRegistryError(409, "enrollment_unavailable", "enrollment invitation is not available")

            invitation["status"] = "claiming"
            invitation["claim_started_at"] = _iso(now)
            invitation["updated_at"] = _iso(now)
            self._save()

        registration = {
            "name": name,
            "type": invitation.get("type"),
            "public_key": public_key,
            "capabilities": payload.get("capabilities") or {},
            "versions": payload.get("versions") or {},
            "groups": list(invitation.get("groups") or []),
            "permissions": list(invitation.get("permissions") or []),
        }

        try:
            device, created = self.registry.register(
                registration,
                actor=f"enrollment:{enrollment_id}",
                client_ip=client_ip,
            )
        except Exception:
            with self._lock:
                invitations = self._state.get("invitations")
                current = invitations.get(enrollment_id) if isinstance(invitations, dict) else None
                if isinstance(current, dict) and current.get("status") == "claiming":
                    current["status"] = "active"
                    current["updated_at"] = _iso(_now())
                    current.pop("claim_started_at", None)
                    self._save()
            raise

        with self._lock:
            invitations = self._state.get("invitations")
            current = invitations.get(enrollment_id) if isinstance(invitations, dict) else None
            if not isinstance(current, dict) or current.get("status") != "claiming":
                raise RuntimeError("enrollment state changed during claim")
            current["status"] = "consumed"
            current["claimed_at"] = _iso(_now())
            current["updated_at"] = current["claimed_at"]
            current["device_id"] = device["device_id"]
            current.pop("claim_started_at", None)
            self._save()
            invitation_public = self._public(dict(current))

        self.audit.append(
            "enrollment.claimed",
            actor=f"device:{device['device_id']}",
            target=enrollment_id,
            client_ip=client_ip,
            details={
                "device_id": device["device_id"],
                "public_key_fingerprint": device.get("public_key_fingerprint"),
                "created": created,
            },
        )
        return {
            "schema": "memoria-server-device-enrollment-claim/v1",
            "status": "pending_approval",
            "device": device,
            "invitation": invitation_public,
        }

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
        if path != PUBLIC_CLAIM_PATH:
            return False
        client_ip = handler.client_address[0] if getattr(handler, "client_address", None) else None
        try:
            if handler.command != "POST":
                handler._write_json(405, {"error": "method_not_allowed"}, {"Allow": "POST"})
                return True
            handler._write_json(201, self.claim(self._json_body(handler), client_ip=client_ip))
            return True
        except DeviceRegistryError as exc:
            handler._write_json(exc.status, {"error": exc.code, "detail": exc.detail})
            return True

    def dispatch_admin(self, handler, path: str) -> bool:
        if path != ADMIN_PREFIX and not path.startswith(ADMIN_PREFIX + "/"):
            return False
        suffix = path[len(ADMIN_PREFIX):].strip("/")
        parts = [part for part in suffix.split("/") if part]
        actor = getattr(handler.config, "admin_username", "admin")
        client_ip = handler.client_address[0] if getattr(handler, "client_address", None) else None
        try:
            if not parts:
                if handler.command in {"GET", "HEAD"}:
                    handler._write_json(200, self.list())
                    return True
                if handler.command == "POST":
                    handler._write_json(
                        201,
                        self.create(self._json_body(handler), actor=actor, client_ip=client_ip),
                    )
                    return True
                handler._write_json(405, {"error": "method_not_allowed"}, {"Allow": "GET, HEAD, POST"})
                return True
            if len(parts) == 2 and parts[1] == "revoke":
                if handler.command != "POST":
                    handler._write_json(405, {"error": "method_not_allowed"}, {"Allow": "POST"})
                    return True
                handler._write_json(
                    200,
                    self.revoke(parts[0], actor=actor, client_ip=client_ip),
                )
                return True
            handler._write_json(404, {"error": "route_not_found"})
            return True
        except DeviceRegistryError as exc:
            handler._write_json(exc.status, {"error": exc.code, "detail": exc.detail})
            return True
