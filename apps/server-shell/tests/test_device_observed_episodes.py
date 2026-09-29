from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace

from device_observed_episodes import (
    OBSERVE_PATH, PRODUCT_PATH, RECEIPT_SCHEMA, DeviceObservedEpisodes, _canonical,
)
from device_registry import DeviceRegistryError


WORLD = "nov-live-autonomous-001"
DEVICE_ID = "dev-live-1"


def envelope():
    identity = {"system": "live.infinita", "world_id": WORLD,
                "entity_id": "nov", "episode_id": "plan:plan_1"}
    unsigned = {
        "schema": "live-infinita-npc-episode-observation/v1",
        "record_key": sha256(_canonical(identity)).hexdigest(),
        "source": {**identity, "source_schema": "npc_episode_v1",
                   "source_kind": "need_outcome", "plan_id": "plan_1",
                   "proposal_id": "pr_1", "plan_revision": 0},
        "observation": {"logical_tick": 12, "need": "curiosity",
                        "target_entity_id": "ancient_tree", "strategy_id": "direct",
                        "context": {"period": "night", "weather": "clear",
                                    "region_id": "clearing", "danger_level": 0.35},
                        "outcome": {"satisfaction": 0.3, "observed_risk": 0.35,
                                    "elapsed_ticks": 3, "preemptions": 0, "replans": 0}},
        "authority": "observed-outcome-only", "world_write_authority": False,
    }
    return {**unsigned, "content_sha256": sha256(_canonical(unsigned)).hexdigest()}


class Auth:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def authenticate(self, token, *, required_permission=None, client_ip=None):
        self.calls.append((token, required_permission, client_ip))
        if self.error:
            raise self.error
        return DEVICE_ID


class Registry:
    def __init__(self, record=None):
        self.record = record or {
            "type": "server", "groups": ["live-world:" + WORLD],
        }
    def get(self, device_id):
        assert device_id == DEVICE_ID
        return self.record


class Handler:
    def __init__(self, body=None, *, command="POST"):
        self.command = command
        self.client_address = ("127.0.0.1", 12345)
        self.headers = {"Authorization": "Device signed-token"}
        self.raw = json.dumps(body if body is not None else envelope()).encode("utf-8")
        self.result = None
        self.read_count = 0
    def _read_body(self):
        self.read_count += 1
        return self.raw
    def _write_json(self, status, payload, extra_headers=None):
        self.result = {"status": status, "payload": payload, "headers": extra_headers or {}}


def good_upstream(payload, stored=True):
    return {
        "schema": payload["schema"], "ack": True, "stored": stored,
        "record_key": payload["record_key"],
        "content_sha256": payload["content_sha256"],
        "episode_id": payload["source"]["episode_id"],
        "world_id": payload["source"]["world_id"],
        "evidence_id": "live-obs:" + payload["record_key"][:40],
        "world_mutated": False, "selection_authority": False,
        "persistence": {
            "backend": "bdr", "state_id": "evidence:hash",
            "sha256": "a"*64,
        },
    }


def facade(auth=None, registry=None, sender=None):
    return DeviceObservedEpisodes(
        auth or Auth(), registry or Registry(),
        SimpleNamespace(snapshot=lambda: {"server_id": "server-a"}),
        "http://127.0.0.1:8090", "INTERNAL_ONLY",
        sender=sender or (lambda path, payload: good_upstream(payload)),
    )


def test_device_scoped_observed_episode_receipt_is_durable_and_not_chat():
    events = []
    auth = Auth()
    impl = facade(auth=auth, sender=lambda path, payload: (
        events.append((path, deepcopy(payload))) or good_upstream(payload)
    ))
    handler = Handler()
    assert impl.dispatch(handler, OBSERVE_PATH)
    assert auth.calls == [
        ("Device signed-token", "memory.sync", "127.0.0.1"),
        ("Device signed-token", "world.connect", "127.0.0.1"),
    ]
    assert handler.result["status"] == 201
    receipt = handler.result["payload"]
    assert receipt["schema"] == RECEIPT_SCHEMA
    assert receipt["status"] == "stored"
    assert receipt["server_id"] == "server-a"
    assert receipt["device_id"] == DEVICE_ID
    assert receipt["namespace"] == "live:" + WORLD
    assert receipt["persistence"]["state_id"]
    assert receipt["world_mutated"] is False
    assert receipt["selection_authority"] is False
    assert events[0][0] == PRODUCT_PATH
    assert "X-Memoria-Key" not in events[0][1]
    assert "role" not in events[0][1]
    assert events[0][1]["source"]["source_kind"] == "need_outcome"
    assert "secret" not in json.dumps(receipt).lower()
    assert not impl.dispatch(handler, "/api/v1/episodes")


def test_missing_permission_fails_before_body_and_upstream():
    auth = Auth(error=DeviceRegistryError(403, "device_permission_denied", "no world permission"))
    events = []
    impl = facade(auth=auth, sender=lambda *args: events.append(args) or {})
    handler = Handler()
    assert impl.dispatch(handler, OBSERVE_PATH)
    assert handler.result["status"] == 403
    assert handler.read_count == 0
    assert events == []


def test_world_binding_and_type_are_enforced_by_server_registry():
    for record in (
        {"type": "server", "groups": []},
        {"type": "offia", "groups": ["live-world:" + WORLD]},
        {"type": "server", "groups": ["live-world:another"]},
    ):
        sent = []
        impl = facade(registry=Registry(record), sender=lambda *args: sent.append(args) or {})
        handler = Handler()
        assert impl.dispatch(handler, OBSERVE_PATH)
        assert handler.result["status"] == 403
        assert sent == []


def test_unknown_fields_bad_lineage_and_changed_digest_fail_closed():
    changes = [
        lambda x: x.update(device_id="dev-other"),
        lambda x: x["source"].update(role="assistant"),
        lambda x: x["source"].update(plan_id="not-original"),
        lambda x: x.update(world_write_authority=True),
        lambda x: x.update(content_sha256="0"*64),
    ]
    for change in changes:
        data = envelope()
        change(data)
        seen = []
        handler = Handler(data)
        assert facade(sender=lambda *args: seen.append(args) or {}).dispatch(handler, OBSERVE_PATH)
        assert handler.result["status"] == 422
        assert seen == []


def test_upstream_ack_must_match_identity_digest_and_durable_receipt():
    for change in (
        lambda r: r.update(content_sha256="0"*64),
        lambda r: r.update(ack=False),
        lambda r: r.update(persistence={}),
        lambda r: r.update(world_mutated=True),
        lambda r: r.update(record_key="0"*64),
    ):
        handler = Handler()
        def bad(path, payload):
            reply = good_upstream(payload)
            change(reply)
            return reply
        assert facade(sender=bad).dispatch(handler, OBSERVE_PATH)
        assert handler.result["status"] == 502


def test_upstream_conflict_returns_409_without_confirmation():
    def failed(_path, _payload):
        raise DeviceRegistryError(409, "observation_identity_conflict", "immutable conflict")
    handler = Handler()
    assert facade(sender=failed).dispatch(handler, OBSERVE_PATH)
    assert handler.result["status"] == 409
    assert handler.result["payload"]["error"] == "observation_identity_conflict"


def test_duplicate_receipt_preserves_central_identity():
    handler = Handler()
    assert facade(sender=lambda p, x: good_upstream(x, stored=False)).dispatch(handler, OBSERVE_PATH)
    assert handler.result["status"] == 201
    assert handler.result["payload"]["status"] == "duplicate"


def test_method_is_post_only_and_does_not_authenticate():
    auth = Auth()
    handler = Handler(command="GET")
    assert facade(auth=auth).dispatch(handler, OBSERVE_PATH)
    assert handler.result["status"] == 405
    assert auth.calls == []


def test_internal_hop_keeps_product_api_key_hidden(monkeypatch):
    import device_observed_episodes as module
    observed = {}

    class Response:
        status = 201
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps(good_upstream(envelope())).encode()

    def fake_urlopen(request, timeout):
        observed["key"] = request.headers.get("X-memoria-key")
        observed["url"] = request.full_url
        observed["body"] = json.loads(request.data)
        return Response()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    impl = DeviceObservedEpisodes(
        Auth(), Registry(), SimpleNamespace(snapshot=lambda: {"server_id": "s"}),
        "http://127.0.0.1:8090", "server-admin-key",
    )
    got = impl._post(PRODUCT_PATH, envelope())
    assert got["ack"] is True
    assert observed["key"] == "server-admin-key"
    assert observed["url"].endswith(PRODUCT_PATH)
    assert observed["body"]["schema"] == envelope()["schema"]
