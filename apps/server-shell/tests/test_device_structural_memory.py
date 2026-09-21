from __future__ import annotations

import json
from types import SimpleNamespace

import device_structural_memory as module
from device_registry import DeviceRegistryError
from device_structural_memory import (
    OBSERVE_PATH,
    RESOLVE_PATH,
    DeviceStructuralMemory,
)


class FakeAuth:
    def __init__(self, device_id="dev-test", error=None):
        self.device_id = device_id
        self.error = error
        self.calls = []

    def authenticate(self, authorization, *, required_permission=None, client_ip=None):
        self.calls.append(
            {
                "authorization": authorization,
                "required_permission": required_permission,
                "client_ip": client_ip,
            }
        )
        if self.error is not None:
            raise self.error
        return self.device_id


class FakeHandler:
    def __init__(self, payload, *, authorization="Device token", command="POST"):
        self.command = command
        self.headers = {"Authorization": authorization}
        self.client_address = ("127.0.0.1", 12345)
        self._body = json.dumps(payload).encode("utf-8")
        self.captured = None

    def _read_body(self):
        return self._body

    def _write_json(self, status, payload, extra_headers=None):
        self.captured = {
            "status": status,
            "payload": payload,
            "headers": extra_headers or {},
        }


def test_observe_requires_memory_sync_and_server_owns_structural_identity():
    auth = FakeAuth(device_id="dev-offia-1")
    sent = []
    memory = DeviceStructuralMemory(
        auth,
        "http://memoria",
        "internal-key",
        sender=lambda path, payload: sent.append((path, payload)) or {
            "stored": True,
            "semantic_projection": False,
            "observation_id": "obs-1",
        },
    )
    handler = FakeHandler(
        {
            "text": "Meu gato se chama Alt",
            "sequence": 7,
            "session_id": "chat pessoal 1",
        }
    )

    assert memory.dispatch(handler, OBSERVE_PATH) is True

    assert auth.calls == [
        {
            "authorization": "Device token",
            "required_permission": "memory.sync",
            "client_ip": "127.0.0.1",
        }
    ]
    assert handler.captured["status"] == 201
    assert handler.captured["payload"]["schema"] == "memoria-server-device-structural-text/v1"
    assert handler.captured["payload"]["scope"] == "device"
    assert handler.captured["payload"]["device_id"] == "dev-offia-1"
    assert sent[0][0] == "/api/v1/structural/text/observe"

    forwarded = sent[0][1]
    assert forwarded["hierarchy_id"] == "offia-device:dev-offia-1"
    assert forwarded["source_kind"] == "user"
    assert forwarded["source_id"].startswith("offia-device:dev-offia-1:session:")
    assert "chat pessoal 1" not in forwarded["source_id"]
    assert forwarded["sequence"] == 7
    assert forwarded["text"] == "Meu gato se chama Alt"


def test_device_cannot_choose_hierarchy_source_kind_or_device_id():
    auth = FakeAuth()
    sent = []
    memory = DeviceStructuralMemory(
        auth,
        "http://memoria",
        "internal-key",
        sender=lambda path, payload: sent.append((path, payload)) or {},
    )
    handler = FakeHandler(
        {
            "text": "tentativa",
            "sequence": 1,
            "hierarchy_id": "offia-device:outra-pessoa",
        }
    )

    assert memory.dispatch(handler, OBSERVE_PATH) is True

    assert handler.captured["status"] == 400
    assert handler.captured["payload"]["error"] == "server_owned_field"
    assert sent == []


def test_resolve_is_read_only_upstream_and_uses_same_device_hierarchy():
    auth = FakeAuth(device_id="dev-offia-2")
    sent = []
    memory = DeviceStructuralMemory(
        auth,
        "http://memoria",
        "internal-key",
        sender=lambda path, payload: sent.append((path, payload)) or {
            "status": "HIT",
            "contexts": [{"source_text": "Minha camisa ficou preta"}],
            "semantic_projection": False,
        },
    )
    handler = FakeHandler({"query": "qual a cor da minha camisa?", "limit": 2})

    assert memory.dispatch(handler, RESOLVE_PATH) is True

    assert handler.captured["status"] == 200
    assert handler.captured["payload"]["status"] == "HIT"
    assert sent == [
        (
            "/api/v1/structural/text/resolve",
            {
                "query": "qual a cor da minha camisa?",
                "hierarchy_id": "offia-device:dev-offia-2",
                "limit": 2,
                "max_scan": 2048,
            },
        )
    ]


def test_missing_memory_sync_permission_fails_before_reading_or_forwarding():
    auth = FakeAuth(
        error=DeviceRegistryError(
            403,
            "device_permission_denied",
            "device lacks required permission: memory.sync",
        )
    )
    sent = []
    memory = DeviceStructuralMemory(
        auth,
        "http://memoria",
        "internal-key",
        sender=lambda path, payload: sent.append((path, payload)) or {},
    )
    handler = FakeHandler({"query": "gato"})
    handler._read_body = lambda: (_ for _ in ()).throw(AssertionError("must authenticate first"))

    assert memory.dispatch(handler, RESOLVE_PATH) is True

    assert handler.captured["status"] == 403
    assert handler.captured["payload"]["error"] == "device_permission_denied"
    assert sent == []


def test_internal_upstream_call_keeps_admin_key_on_server(monkeypatch):
    auth = FakeAuth()
    seen = {}

    class Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"stored":true,"semantic_projection":false}'

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["method"] = request.method
        seen["key"] = request.headers.get("X-memoria-key")
        seen["body"] = json.loads(request.data)
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    memory = DeviceStructuralMemory(auth, "http://memoria", "internal-secret", timeout_seconds=4)

    result = memory._post(
        "/api/v1/structural/text/observe",
        {
            "text": "Alt",
            "hierarchy_id": "offia-device:dev-test",
            "source_id": "offia-device:dev-test",
            "sequence": 1,
            "source_kind": "user",
        },
    )

    assert result["stored"] is True
    assert seen["url"] == "http://memoria/api/v1/structural/text/observe"
    assert seen["method"] == "POST"
    assert seen["key"] == "internal-secret"
    assert seen["timeout"] == 4.0
    assert seen["body"]["hierarchy_id"] == "offia-device:dev-test"


def test_structural_device_routes_are_post_only():
    auth = FakeAuth()
    memory = DeviceStructuralMemory(auth, "http://memoria", "key", sender=lambda *_: {})
    handler = FakeHandler({}, command="GET")

    assert memory.dispatch(handler, RESOLVE_PATH) is True

    assert handler.captured["status"] == 405
    assert handler.captured["headers"]["Allow"] == "POST"
    assert auth.calls == []
