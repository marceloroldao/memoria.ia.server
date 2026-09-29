"""Ed25519-scoped intake for Live.infinita witnessed NPC episodes.

Device tokens authorize this boundary. Only the Server holds X-Memoria-Key;
the existing Product EvidenceCore owns canonical durable storage and conflict
detection. The source world's single writer is never called.
"""
from __future__ import annotations

from hashlib import sha256
import hmac
import json
import socket
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from device_registry import DeviceRegistryError

OBSERVE_PATH = "/api/server/v1/device/observations/npc-episodes"
SCHEMA = "live-infinita-npc-episode-observation/v1"
RECEIPT_SCHEMA = "memoria-server-npc-episode-receipt/v1"
PRODUCT_PATH = "/api/v1/external/episodes"


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _validated(payload: dict[str, object]) -> tuple[str, str, str]:
    if set(payload) != {
        "schema", "record_key", "source", "observation", "authority",
        "world_write_authority", "content_sha256",
    }:
        raise DeviceRegistryError(422, "invalid_observation_envelope", "unsupported fields")
    if payload.get("schema") != SCHEMA or payload.get("authority") != "observed-outcome-only":
        raise DeviceRegistryError(422, "invalid_observation_schema", "typed observed outcome required")
    if payload.get("world_write_authority") is not False:
        raise DeviceRegistryError(422, "invalid_observation_authority", "world write authority is forbidden")
    source = payload.get("source")
    observation = payload.get("observation")
    if not isinstance(source, dict) or not isinstance(observation, dict):
        raise DeviceRegistryError(422, "invalid_observation", "source and observation must be objects")
    expected_source = {
        "system", "world_id", "entity_id", "episode_id", "source_schema",
        "source_kind", "plan_id", "proposal_id", "plan_revision",
    }
    if set(source) != expected_source:
        raise DeviceRegistryError(422, "invalid_source_fields", "source provenance is incomplete")
    world_id = source.get("world_id")
    episode_id = source.get("episode_id")
    plan_id = source.get("plan_id")
    proposal_id = source.get("proposal_id")
    revision = source.get("plan_revision")
    if (
        source.get("system") != "live.infinita"
        or source.get("entity_id") != "nov"
        or source.get("source_schema") != "npc_episode_v1"
        or source.get("source_kind") != "need_outcome"
        or not isinstance(world_id, str)
        or not 1 <= len(world_id) <= 96
        or not all(ch.isascii() and (ch.isalnum() or ch in "._:-") for ch in world_id)
        or not isinstance(plan_id, str) or not plan_id
        or not isinstance(proposal_id, str) or not proposal_id
        or not isinstance(episode_id, str) or episode_id != "plan:" + plan_id
        or isinstance(revision, bool) or not isinstance(revision, int)
        or not 0 <= revision <= 1_000_000
    ):
        raise DeviceRegistryError(422, "invalid_source_provenance", "confirmed plan outcome required")
    if not isinstance(payload.get("record_key"), str) or not isinstance(payload.get("content_sha256"), str):
        raise DeviceRegistryError(422, "invalid_observation_digest", "digests required")
    identity = {
        "system": "live.infinita", "world_id": world_id,
        "entity_id": "nov", "episode_id": episode_id,
    }
    try:
        record_key = sha256(_canonical(identity)).hexdigest()
        unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
        content_sha256 = sha256(_canonical(unsigned)).hexdigest()
    except (TypeError, ValueError, OverflowError) as exc:
        raise DeviceRegistryError(422, "invalid_observation_content", "non-canonical observation") from exc
    if not hmac.compare_digest(record_key, payload["record_key"]) or not hmac.compare_digest(content_sha256, payload["content_sha256"]):
        raise DeviceRegistryError(422, "observation_digest_mismatch", "record identity or digest mismatch")
    return world_id, record_key, content_sha256


class DeviceObservedEpisodes:
    def __init__(
        self, device_auth, registry, identity, memoria_api_url: str, memoria_api_key: str,
        *, timeout_seconds: float = 10.0,
        sender: Callable[[str, dict[str, object]], dict[str, object]] | None = None,
    ) -> None:
        self.device_auth = device_auth
        self.registry = registry
        self.identity = identity
        self.memoria_api_url = memoria_api_url.rstrip("/")
        self.memoria_api_key = memoria_api_key
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.sender = sender or self._post

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        if not self.memoria_api_key:
            raise DeviceRegistryError(503, "central_memory_not_configured", "internal memory key unavailable")
        request = Request(
            self.memoria_api_url + path,
            data=_canonical(payload),
            headers={
                "Content-Type": "application/json", "Accept": "application/json",
                "X-Memoria-Key": self.memoria_api_key,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                row = json.loads(response.read().decode("utf-8"))
                if response.status != 201 or not isinstance(row, dict):
                    raise ValueError("invalid upstream receipt")
                return row
        except HTTPError as exc:
            # Only immutable-identity conflicts are exposed to the client;
            # upstream credentials, internal validation and URLs remain private.
            if exc.code == 409:
                raise DeviceRegistryError(409, "observation_identity_conflict", "central observation identity conflict") from exc
            raise DeviceRegistryError(502, "central_memory_rejected", "central memory rejected observation") from exc
        except (URLError, socket.timeout, TimeoutError, OSError) as exc:
            raise DeviceRegistryError(502, "central_memory_unavailable", "central memory unavailable") from exc
        except (UnicodeError, ValueError) as exc:
            raise DeviceRegistryError(502, "invalid_central_receipt", "central memory returned invalid receipt") from exc

    def dispatch(self, handler, path: str) -> bool:
        if path != OBSERVE_PATH:
            return False
        client_ip = handler.client_address[0] if getattr(handler, "client_address", None) else None
        try:
            if handler.command != "POST":
                handler._write_json(405, {"error": "method_not_allowed"}, {"Allow": "POST"})
                return True
            authorization = handler.headers.get("Authorization", "")
            device_id = self.device_auth.authenticate(
                authorization, required_permission="memory.sync", client_ip=client_ip,
            )
            same_device = self.device_auth.authenticate(
                authorization, required_permission="world.connect", client_ip=client_ip,
            )
            if same_device != device_id:
                raise DeviceRegistryError(403, "device_identity_changed", "device identity changed")
            device = self.registry.get(device_id)
            if device.get("type") != "server":
                raise DeviceRegistryError(403, "world_device_type_required", "approved server device required")

            raw = handler._read_body()
            if raw is None:
                return True
            try:
                payload = json.loads(raw.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (UnicodeError, ValueError) as exc:
                raise DeviceRegistryError(400, "invalid_json", "JSON object required") from exc
            if not isinstance(payload, dict):
                raise DeviceRegistryError(400, "invalid_json", "JSON object required")
            world_id, record_key, digest = _validated(payload)
            if "live-world:" + world_id not in set(device.get("groups") or []):
                raise DeviceRegistryError(403, "world_binding_required", "world not approved for this device")

            upstream = self.sender(PRODUCT_PATH, payload)
            persistence = upstream.get("persistence")
            if not (
                upstream.get("schema") == SCHEMA
                and upstream.get("ack") is True
                and isinstance(upstream.get("stored"), bool)
                and upstream.get("record_key") == record_key
                and upstream.get("content_sha256") == digest
                and upstream.get("world_id") == world_id
                and upstream.get("episode_id") == payload["source"]["episode_id"]
                and upstream.get("world_mutated") is False
                and upstream.get("selection_authority") is False
                and isinstance(upstream.get("evidence_id"), str)
                and bool(upstream["evidence_id"])
                and isinstance(persistence, dict)
                and all(isinstance(persistence.get(k), str) and persistence[k] for k in ("backend", "state_id", "sha256"))
            ):
                raise DeviceRegistryError(502, "invalid_central_receipt", "central durable receipt mismatch")
            handler._write_json(201, {
                "schema": RECEIPT_SCHEMA,
                "status": "stored" if upstream["stored"] else "duplicate",
                "record_key": record_key,
                "content_sha256": digest,
                "episode_id": payload["source"]["episode_id"],
                "namespace": "live:" + world_id,
                "server_id": self.identity.snapshot()["server_id"],
                "device_id": device_id,
                "evidence_id": upstream["evidence_id"],
                "persistence": persistence,
                "world_mutated": False,
                "selection_authority": False,
            })
            return True
        except DeviceRegistryError as exc:
            handler._write_json(exc.status, {"error": exc.code, "detail": exc.detail})
            return True
