"""Device-authenticated structural text memory facade.

This module keeps Memoria.ia's administrative API key on the server. Devices
authenticate with the Server's Ed25519 challenge/token flow and need the
`memory.sync` permission. Structural hierarchy ownership is derived from the
authenticated device_id and cannot be selected by the client.
"""
from __future__ import annotations

import hashlib
import json
import socket
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from device_auth import DeviceAuthManager
from device_registry import DeviceRegistryError


OBSERVE_PATH = "/api/server/v1/device/memory/structural/observe"
RESOLVE_PATH = "/api/server/v1/device/memory/structural/resolve"
SCHEMA = "memoria-server-device-structural-text/v1"


class DeviceStructuralMemory:
    def __init__(
        self,
        device_auth: DeviceAuthManager,
        memoria_api_url: str,
        memoria_api_key: str,
        *,
        timeout_seconds: float = 10.0,
        sender: Callable[[str, dict[str, object]], dict[str, object]] | None = None,
    ) -> None:
        self.device_auth = device_auth
        self.memoria_api_url = memoria_api_url.rstrip("/")
        self.memoria_api_key = memoria_api_key
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.sender = sender or self._post

    @staticmethod
    def _hierarchy_id(device_id: str) -> str:
        return f"offia-device:{device_id}"

    @staticmethod
    def _source_id(device_id: str, session_id: str) -> str:
        session = session_id.strip()
        if not session:
            return f"offia-device:{device_id}"
        digest = hashlib.sha256(session.encode("utf-8")).hexdigest()[:24]
        return f"offia-device:{device_id}:session:{digest}"

    @staticmethod
    def _json_body(handler) -> dict[str, object]:
        body = handler._read_body()
        if body is None:
            raise DeviceRegistryError(400, "invalid_request", "request body could not be read")
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeviceRegistryError(400, "invalid_json", "JSON object required") from exc
        if not isinstance(payload, dict):
            raise DeviceRegistryError(400, "invalid_json", "JSON object required")
        return payload

    @staticmethod
    def _reject_ownership_fields(payload: dict[str, object]) -> None:
        forbidden = {"hierarchy_id", "source_id", "source_kind", "device_id"}
        supplied = sorted(forbidden.intersection(payload))
        if supplied:
            raise DeviceRegistryError(
                400,
                "server_owned_field",
                "server-owned fields are not accepted: " + ", ".join(supplied),
            )

    @staticmethod
    def _observe_payload(payload: dict[str, object], device_id: str) -> dict[str, object]:
        DeviceStructuralMemory._reject_ownership_fields(payload)
        allowed = {"text", "sequence", "session_id"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise DeviceRegistryError(400, "unknown_field", "unknown fields: " + ", ".join(unknown))

        text = str(payload.get("text") or "").strip()
        if not text:
            raise DeviceRegistryError(422, "text_required", "text is required")
        if len(text) > 20_000:
            raise DeviceRegistryError(422, "text_too_large", "text exceeds 20000 characters")

        sequence = payload.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise DeviceRegistryError(422, "invalid_sequence", "sequence must be an integer >= 0")

        session_id = str(payload.get("session_id") or "").strip()
        if len(session_id) > 256:
            raise DeviceRegistryError(422, "session_id_too_large", "session_id exceeds 256 characters")

        return {
            "text": text,
            "hierarchy_id": DeviceStructuralMemory._hierarchy_id(device_id),
            "source_id": DeviceStructuralMemory._source_id(device_id, session_id),
            "sequence": sequence,
            "source_kind": "user",
        }

    @staticmethod
    def _resolve_payload(payload: dict[str, object], device_id: str) -> dict[str, object]:
        DeviceStructuralMemory._reject_ownership_fields(payload)
        allowed = {"query", "limit", "max_scan"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise DeviceRegistryError(400, "unknown_field", "unknown fields: " + ", ".join(unknown))

        query = str(payload.get("query") or "").strip()
        if not query:
            raise DeviceRegistryError(422, "query_required", "query is required")
        if len(query) > 4_000:
            raise DeviceRegistryError(422, "query_too_large", "query exceeds 4000 characters")

        limit = payload.get("limit", 3)
        max_scan = payload.get("max_scan", 2048)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise DeviceRegistryError(422, "invalid_limit", "limit must be an integer between 1 and 20")
        if isinstance(max_scan, bool) or not isinstance(max_scan, int) or not 1 <= max_scan <= 100_000:
            raise DeviceRegistryError(422, "invalid_max_scan", "max_scan must be an integer between 1 and 100000")

        return {
            "query": query,
            "hierarchy_id": DeviceStructuralMemory._hierarchy_id(device_id),
            "limit": limit,
            "max_scan": max_scan,
        }

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.memoria_api_key:
            headers["X-Memoria-Key"] = self.memoria_api_key
        request = Request(self.memoria_api_url + path, data=data, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8") or "{}")
                if response.status not in {200, 201} or not isinstance(body, dict):
                    raise RuntimeError("structural memory returned an invalid response")
                return body
        except HTTPError as exc:
            raw = exc.read().decode(errors="replace")[:500]
            try:
                detail = json.loads(raw or "{}")
            except json.JSONDecodeError:
                detail = {"detail": raw}
            raise DeviceRegistryError(
                exc.code if 400 <= exc.code < 500 else 502,
                "structural_memory_upstream_rejected",
                json.dumps(detail, ensure_ascii=False, separators=(",", ":")),
            ) from exc
        except (URLError, socket.timeout, TimeoutError, OSError) as exc:
            raise DeviceRegistryError(
                502,
                "structural_memory_upstream_unavailable",
                "Memoria.ia structural memory is unavailable",
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
            raise DeviceRegistryError(
                502,
                "structural_memory_upstream_invalid",
                "Memoria.ia structural memory returned an invalid response",
            ) from exc

    @staticmethod
    def _response(device_id: str, upstream: dict[str, object]) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "scope": "device",
            "device_id": device_id,
            **upstream,
        }

    def dispatch(self, handler, path: str) -> bool:
        if path not in {OBSERVE_PATH, RESOLVE_PATH}:
            return False

        client_ip = handler.client_address[0] if getattr(handler, "client_address", None) else None
        try:
            if handler.command != "POST":
                handler._write_json(405, {"error": "method_not_allowed"}, {"Allow": "POST"})
                return True

            device_id = self.device_auth.authenticate(
                handler.headers.get("Authorization", ""),
                required_permission="memory.sync",
                client_ip=client_ip,
            )
            payload = self._json_body(handler)

            if path == OBSERVE_PATH:
                upstream_payload = self._observe_payload(payload, device_id)
                upstream = self.sender("/api/v1/structural/text/observe", upstream_payload)
                handler._write_json(201, self._response(device_id, upstream))
            else:
                upstream_payload = self._resolve_payload(payload, device_id)
                upstream = self.sender("/api/v1/structural/text/resolve", upstream_payload)
                handler._write_json(200, self._response(device_id, upstream))
            return True
        except DeviceRegistryError as exc:
            handler._write_json(exc.status, {"error": exc.code, "detail": exc.detail})
            return True
