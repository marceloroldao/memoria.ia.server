"""Persistent server-owned identity, device registry and audit log.

This module deliberately lives in memoria.ia.server. It stores operational
metadata in server-data and never writes semantic memory or BDR state.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

DEVICE_PREFIX = "/api/server/v1/devices"
IDENTITY_PATH = "/api/server/v1/server/identity"
AUDIT_PATH = "/api/server/v1/audit"

_ALLOWED_TYPES = {"offia", "phone", "computer", "server", "robot", "sensor", "iot"}
_ALLOWED_STATUSES = {"pending", "active", "suspended", "revoked"}
_SECRET_MARKERS = ("password", "secret", "api_key", "private_key", "token", "credential")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any], *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        temporary.unlink(missing_ok=True)


def _clean_list(value: object, *, max_items: int = 64, max_length: int = 128) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DeviceRegistryError(422, "invalid_list", "expected a JSON list")
    result: list[str] = []
    seen: set[str] = set()
    for item in value[:max_items]:
        text = str(item).strip()
        if not text:
            continue
        text = text[:max_length]
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _clean_mapping(value: object, *, allowed: set[str], max_string: int = 256) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise DeviceRegistryError(422, "invalid_object", "expected a JSON object")
    result: dict[str, object] = {}
    for key in allowed:
        if key not in value:
            continue
        item = value[key]
        if item is None or isinstance(item, (bool, int, float)):
            result[key] = item
        elif isinstance(item, str):
            result[key] = item[:max_string]
        elif isinstance(item, list):
            result[key] = _clean_list(item)
    return result


def _scrub(value: object) -> object:
    if isinstance(value, dict):
        clean: dict[str, object] = {}
        for key, item in value.items():
            lowered = str(key).casefold()
            clean[str(key)] = "[redacted]" if any(marker in lowered for marker in _SECRET_MARKERS) else _scrub(item)
        return clean
    if isinstance(value, list):
        return [_scrub(item) for item in value[:100]]
    if isinstance(value, str):
        return value[:1000]
    return value


class DeviceRegistryError(RuntimeError):
    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail


class ServerIdentity:
    SCHEMA = "memoria-server-identity/v1"

    def __init__(self, data_dir: str | Path) -> None:
        self.root = Path(data_dir)
        self.path = self.root / "server-identity.json"
        self._lock = RLock()
        self._identity = self._load_or_create()

    def _load_or_create(self) -> dict[str, object]:
        try:
            payload = json.loads(self.path.read_text("utf-8"))
            if (
                isinstance(payload, dict)
                and payload.get("schema") == self.SCHEMA
                and isinstance(payload.get("server_id"), str)
                and payload["server_id"]
            ):
                return payload
        except (OSError, json.JSONDecodeError):
            pass
        payload = {
            "schema": self.SCHEMA,
            "server_id": "srv-" + uuid4().hex,
            "created_at": _now(),
        }
        _atomic_json(self.path, payload)
        return payload

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return dict(self._identity)


class AuditLog:
    SCHEMA = "memoria-server-audit/v1"

    def __init__(self, data_dir: str | Path) -> None:
        self.root = Path(data_dir)
        self.path = self.root / "audit.jsonl"
        self._lock = RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        self._sequence = self._last_sequence()

    def _last_sequence(self) -> int:
        if not self.path.exists():
            return 0
        last = ""
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        last = line
            return int(json.loads(last).get("sequence") or 0) if last else 0
        except Exception:
            return 0

    def append(
        self,
        action: str,
        *,
        actor: str,
        target: str | None = None,
        client_ip: str | None = None,
        details: dict[str, object] | None = None,
    ) -> dict[str, object]:
        with self._lock:
            self._sequence += 1
            event = {
                "schema": self.SCHEMA,
                "sequence": self._sequence,
                "timestamp": _now(),
                "actor": actor[:128],
                "action": action[:128],
                "target": (target or "")[:256] or None,
                "client_ip": (client_ip or "")[:64] or None,
                "details": _scrub(details or {}),
            }
            line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                with os.fdopen(fd, "a", encoding="utf-8") as handle:
                    handle.write(line)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(self.path, 0o600)
            finally:
                pass
            return event

    def recent(self, limit: int = 100) -> dict[str, object]:
        limit = max(1, min(int(limit), 1000))
        rows: list[dict[str, object]] = []
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(item, dict):
                            rows.append(item)
            except OSError:
                rows = []
        return {
            "schema": self.SCHEMA,
            "count": min(len(rows), limit),
            "total_sequence": self._sequence,
            "events": rows[-limit:],
        }


class DeviceRegistry:
    SCHEMA = "memoria-server-device-registry/v1"
    DEVICE_SCHEMA = "memoria-server-device/v1"

    def __init__(self, data_dir: str | Path, identity: ServerIdentity, audit: AuditLog) -> None:
        self.root = Path(data_dir)
        self.path = self.root / "devices.json"
        self.identity = identity
        self.audit = audit
        self._lock = RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict[str, object]:
        try:
            payload = json.loads(self.path.read_text("utf-8"))
            if isinstance(payload, dict) and payload.get("schema") == self.SCHEMA and isinstance(payload.get("devices"), dict):
                return payload
        except (OSError, json.JSONDecodeError):
            pass
        return {"schema": self.SCHEMA, "updated_at": _now(), "devices": {}}

    def _save(self) -> None:
        self._state["updated_at"] = _now()
        _atomic_json(self.path, self._state)

    @staticmethod
    def _capabilities(value: object) -> dict[str, object]:
        return _clean_mapping(
            value,
            allowed={"cpu", "gpu", "npu", "ram_bytes", "storage_bytes", "models", "network", "architecture"},
        )

    @staticmethod
    def _versions(value: object) -> dict[str, object]:
        return _clean_mapping(
            value,
            allowed={"offia", "memoria", "bdr", "ma2a", "firmware", "os"},
        )

    @staticmethod
    def _public_key(payload: dict[str, object]) -> str:
        public_key = str(payload.get("public_key") or "").strip()
        if len(public_key) < 16 or len(public_key) > 8192:
            raise DeviceRegistryError(422, "invalid_public_key", "public_key must contain 16 to 8192 characters")
        return public_key

    @staticmethod
    def _fingerprint(public_key: str) -> str:
        return "sha256:" + hashlib.sha256(public_key.encode("utf-8")).hexdigest()

    def register(
        self,
        payload: dict[str, object],
        *,
        actor: str,
        client_ip: str | None = None,
    ) -> tuple[dict[str, object], bool]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise DeviceRegistryError(422, "invalid_name", "device name is required")
        device_type = str(payload.get("type") or "").strip().casefold()
        if device_type not in _ALLOWED_TYPES:
            raise DeviceRegistryError(422, "invalid_type", "unsupported device type")
        public_key = self._public_key(payload)
        fingerprint = self._fingerprint(public_key)
        capabilities = self._capabilities(payload.get("capabilities"))
        versions = self._versions(payload.get("versions"))
        groups = _clean_list(payload.get("groups"), max_items=32)
        permissions = _clean_list(payload.get("permissions"), max_items=64)
        now = _now()

        with self._lock:
            devices = self._state["devices"]
            assert isinstance(devices, dict)
            for existing in devices.values():
                if isinstance(existing, dict) and existing.get("public_key_fingerprint") == fingerprint and existing.get("status") != "revoked":
                    return dict(existing), False

            device_id = "dev-" + uuid4().hex
            record: dict[str, object] = {
                "schema": self.DEVICE_SCHEMA,
                "device_id": device_id,
                "server_id": self.identity.snapshot()["server_id"],
                "name": name[:160],
                "type": device_type,
                "status": "pending",
                "public_key": public_key,
                "public_key_fingerprint": fingerprint,
                "certificate_status": "not_issued",
                "capabilities": capabilities,
                "versions": versions,
                "groups": groups,
                "permissions": permissions,
                "created_at": now,
                "updated_at": now,
                "approved_at": None,
                "suspended_at": None,
                "revoked_at": None,
                "last_seen": None,
            }
            devices[device_id] = record
            self._save()

        self.audit.append(
            "device.register",
            actor=actor,
            target=device_id,
            client_ip=client_ip,
            details={"name": name, "type": device_type, "public_key_fingerprint": fingerprint},
        )
        return dict(record), True

    def _record(self, device_id: str) -> dict[str, object]:
        devices = self._state.get("devices")
        item = devices.get(device_id) if isinstance(devices, dict) else None
        if not isinstance(item, dict):
            raise DeviceRegistryError(404, "device_not_found", "device not found")
        return item

    def get(self, device_id: str) -> dict[str, object]:
        with self._lock:
            return dict(self._record(device_id))

    def list(self, *, status: str | None = None, device_type: str | None = None) -> dict[str, object]:
        if status and status not in _ALLOWED_STATUSES:
            raise DeviceRegistryError(422, "invalid_status", "unsupported device status")
        if device_type and device_type not in _ALLOWED_TYPES:
            raise DeviceRegistryError(422, "invalid_type", "unsupported device type")
        with self._lock:
            devices = self._state.get("devices")
            rows = [dict(item) for item in (devices or {}).values() if isinstance(item, dict)] if isinstance(devices, dict) else []
        if status:
            rows = [item for item in rows if item.get("status") == status]
        if device_type:
            rows = [item for item in rows if item.get("type") == device_type]
        rows.sort(key=lambda item: (str(item.get("status")), str(item.get("name")).casefold(), str(item.get("device_id"))))
        return {"schema": self.SCHEMA, "count": len(rows), "devices": rows}

    def stats(self) -> dict[str, int]:
        rows = self.list()["devices"]
        counts = {key: 0 for key in _ALLOWED_STATUSES}
        for item in rows:
            status = str(item.get("status") or "")
            if status in counts:
                counts[status] += 1
        return {"total": len(rows), **counts}

    def _transition(
        self,
        device_id: str,
        target_status: str,
        *,
        actor: str,
        client_ip: str | None,
    ) -> dict[str, object]:
        now = _now()
        with self._lock:
            item = self._record(device_id)
            current = str(item.get("status") or "")
            if current == "revoked":
                raise DeviceRegistryError(409, "device_revoked", "revoked devices cannot change state")
            if target_status == "active" and current not in {"pending", "suspended", "active"}:
                raise DeviceRegistryError(409, "invalid_transition", f"cannot activate device from {current}")
            if target_status == "suspended" and current not in {"active", "suspended"}:
                raise DeviceRegistryError(409, "invalid_transition", f"cannot suspend device from {current}")
            if target_status == "revoked" and current == "revoked":
                raise DeviceRegistryError(409, "device_revoked", "device is already revoked")
            item["status"] = target_status
            item["updated_at"] = now
            if target_status == "active":
                item["approved_at"] = item.get("approved_at") or now
                item["suspended_at"] = None
            elif target_status == "suspended":
                item["suspended_at"] = now
            elif target_status == "revoked":
                item["revoked_at"] = now
            self._save()
            result = dict(item)

        self.audit.append(
            f"device.{target_status}",
            actor=actor,
            target=device_id,
            client_ip=client_ip,
            details={"from": current, "to": target_status},
        )
        return result

    def approve(self, device_id: str, *, actor: str, client_ip: str | None = None) -> dict[str, object]:
        return self._transition(device_id, "active", actor=actor, client_ip=client_ip)

    def suspend(self, device_id: str, *, actor: str, client_ip: str | None = None) -> dict[str, object]:
        return self._transition(device_id, "suspended", actor=actor, client_ip=client_ip)

    def revoke(self, device_id: str, *, actor: str, client_ip: str | None = None) -> dict[str, object]:
        return self._transition(device_id, "revoked", actor=actor, client_ip=client_ip)

    def heartbeat(
        self,
        device_id: str,
        payload: dict[str, object],
        *,
        actor: str,
        client_ip: str | None = None,
    ) -> dict[str, object]:
        now = _now()
        with self._lock:
            item = self._record(device_id)
            if item.get("status") != "active":
                raise DeviceRegistryError(409, "device_not_active", "heartbeat is accepted only for active devices")
            if "capabilities" in payload:
                item["capabilities"] = self._capabilities(payload.get("capabilities"))
            if "versions" in payload:
                item["versions"] = self._versions(payload.get("versions"))
            item["last_seen"] = now
            item["updated_at"] = now
            self._save()
            result = dict(item)

        self.audit.append(
            "device.heartbeat",
            actor=actor,
            target=device_id,
            client_ip=client_ip,
            details={"last_seen": now, "capabilities_updated": "capabilities" in payload, "versions_updated": "versions" in payload},
        )
        return result

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

    def dispatch(self, handler, path: str, query: dict[str, list[str]]) -> bool:
        if path != DEVICE_PREFIX and not path.startswith(DEVICE_PREFIX + "/"):
            return False
        suffix = path[len(DEVICE_PREFIX):].strip("/")
        parts = [part for part in suffix.split("/") if part]
        actor = getattr(handler.config, "admin_username", "admin")
        client_ip = handler.client_address[0] if getattr(handler, "client_address", None) else None

        try:
            if not parts:
                if handler.command in {"GET", "HEAD"}:
                    status = (query.get("status") or [None])[0]
                    device_type = (query.get("type") or [None])[0]
                    handler._write_json(200, self.list(status=status, device_type=device_type))
                    return True
                handler._write_json(405, {"error": "method_not_allowed"}, {"Allow": "GET, HEAD"})
                return True

            if parts == ["register"]:
                if handler.command != "POST":
                    handler._write_json(405, {"error": "method_not_allowed"}, {"Allow": "POST"})
                    return True
                record, created = self.register(self._json_body(handler), actor=actor, client_ip=client_ip)
                handler._write_json(201 if created else 200, {"created": created, "device": record})
                return True

            device_id = parts[0]
            if len(parts) == 1:
                if handler.command not in {"GET", "HEAD"}:
                    handler._write_json(405, {"error": "method_not_allowed"}, {"Allow": "GET, HEAD"})
                    return True
                handler._write_json(200, self.get(device_id))
                return True

            if len(parts) == 2 and parts[1] in {"approve", "suspend", "revoke", "heartbeat"}:
                if handler.command != "POST":
                    handler._write_json(405, {"error": "method_not_allowed"}, {"Allow": "POST"})
                    return True
                action = parts[1]
                if action == "approve":
                    result = self.approve(device_id, actor=actor, client_ip=client_ip)
                elif action == "suspend":
                    result = self.suspend(device_id, actor=actor, client_ip=client_ip)
                elif action == "revoke":
                    result = self.revoke(device_id, actor=actor, client_ip=client_ip)
                else:
                    result = self.heartbeat(device_id, self._json_body(handler), actor=actor, client_ip=client_ip)
                handler._write_json(200, result)
                return True

            raise DeviceRegistryError(404, "route_not_found", "device route not found")
        except DeviceRegistryError as exc:
            handler._write_json(exc.status, {"error": exc.code, "detail": exc.detail})
            return True
