from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace
from threading import Lock
import json
import sys

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from config import ShellConfig
import server
from server import proxy_target, server_capabilities, static_target


def test_memoria_namespace_is_preserved():
    config = ShellConfig(memoria_api_url="http://memoria", bdr_explorer_url="http://bdr")
    assert proxy_target(config, "/api/v1/admin/status") == (
        "http://memoria",
        "/api/v1/admin/status",
    )


def test_bdr_namespace_is_unwrapped_for_original_explorer_api():
    config = ShellConfig(memoria_api_url="http://memoria", bdr_explorer_url="http://bdr")
    assert proxy_target(config, "/api/bdr-explorer/v1/snapshot") == (
        "http://bdr",
        "/api/snapshot",
    )


def test_unknown_api_is_not_an_open_proxy():
    assert proxy_target(ShellConfig(), "/api/unknown") is None


def test_model_catalog_namespace_is_sent_to_gateway():
    config = ShellConfig(model_gateway_url="http://gateway")
    assert proxy_target(config, "/api/server/v1/models") == (
        "http://gateway",
        "/admin/models",
    )
    assert proxy_target(config, "/api/server/v1/models/local/activate") == (
        "http://gateway",
        "/admin/models/local/activate",
    )


def test_module_static_routes_are_explicit():
    assert static_target("/admin/memoria").name == "index.html"
    assert static_target("/explorer/bdr/app.js").name == "app.js"
    assert static_target("/../../etc/passwd") is None



def test_server_owned_static_routes_include_devices_and_admin_diagnostics_fix():
    assert static_target("/devices").name == "devices.html"
    assert static_target("/devices.js").name == "devices.js"
    assert static_target("/admin/memoria/diagnostics-fix.js").name == "diagnostics-fix.js"


def test_server_capabilities_do_not_advertise_unimplemented_bdr_format():
    capabilities = server_capabilities()
    assert capabilities["device_registry_v1"] is True
    assert capabilities["device_auth_v1"] is True
    assert capabilities["device_certificates_v1"] is True
    assert capabilities["device_permissions_v1"] is True
    assert capabilities["device_enrollment_v1"] is True
    assert capabilities["device_structural_text_memory_v1"] is True
    assert capabilities["audit_log_v1"] is True
    assert capabilities["format_bdr"] is True



def test_server_ready_returns_503_when_any_dependency_is_degraded():
    handler = object.__new__(__import__("server").ShellHandler)
    captured = {}
    handler._health_payload = lambda: {
        "status": "degraded",
        "components": {
            "memoria": {"status": "offline"},
            "bdr_explorer": {"status": "online"},
            "model_gateway": {"status": "online"},
        },
    }
    handler._write_json = lambda status, payload: captured.update(status=status, payload=payload)

    __import__("server").ShellHandler._ready(handler)

    assert captured["status"] == 503
    assert captured["payload"]["ready"] is False
    assert captured["payload"]["components"]["memoria"]["status"] == "offline"


def test_server_ready_returns_200_when_all_dependencies_are_online():
    handler = object.__new__(__import__("server").ShellHandler)
    captured = {}
    handler._health_payload = lambda: {
        "status": "online",
        "components": {
            "memoria": {"status": "online"},
            "bdr_explorer": {"status": "online"},
            "model_gateway": {"status": "online"},
        },
    }
    handler._write_json = lambda status, payload: captured.update(status=status, payload=payload)

    __import__("server").ShellHandler._ready(handler)

    assert captured["status"] == 200
    assert captured["payload"]["ready"] is True


class _FormatCuriosity:
    def __init__(self):
        self.state = SimpleNamespace(enabled=True)
        self.actions = []
        self.reset_calls = []
    def action(self, value):
        self.actions.append(value)
        self.state.enabled = value != "pause"
        return {}
    def reset_cognitive_state(self, *, enabled=None):
        self.reset_calls.append(enabled)
        self.state.enabled = bool(enabled)
        return {"curiosity_reset": True, "raw_web_preserved": True, "enabled": bool(enabled)}


class _Resettable:
    def __init__(self, result):
        self.calls = 0
        self.result = result
    def reset(self):
        self.calls += 1
        return dict(self.result)


class _FormatLearner:
    def __init__(self):
        self.reset_calls = 0
    def format_guard(self):
        return nullcontext()
    def reset_after_format(self):
        self.reset_calls += 1
        return {"learning_cursor_reset": True}


def _format_handler(body=b'{"confirm":"FORMATAR"}'):
    handler = object.__new__(server.ShellHandler)
    handler.command = "POST"
    handler.config = SimpleNamespace(
        memoria_api_url="http://memoria",
        memoria_api_key="internal-key",
        proxy_timeout_seconds=3.0,
    )
    handler.curiosity = _FormatCuriosity()
    handler.knowledge = _Resettable({})
    handler.trajectories = _Resettable({"trajectories_reset": True})
    handler.learner = _FormatLearner()
    handler.episode_write_lock = Lock()
    handler._read_body = lambda: body
    captured = {}
    handler._write_json = lambda status, payload, extra_headers=None: captured.update(status=status, payload=payload)
    return handler, captured


def test_format_bdr_requires_exact_confirmation(monkeypatch):
    handler, captured = _format_handler(b'{"confirm":"nao"}')
    monkeypatch.setattr(server, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not call upstream")))

    server.ShellHandler._format_bdr(handler)

    assert captured["status"] == 400
    assert handler.curiosity.actions == []
    assert handler.knowledge.calls == 0


def test_format_bdr_clears_derived_state_only_after_upstream_success(monkeypatch):
    handler, captured = _format_handler()
    seen = {}

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps({
                "status": "OK",
                "removed_turns": 10,
                "removed_episodes": 20,
                "wal_preserved": True,
            }).encode()

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["method"] = request.method
        seen["key"] = request.headers.get("X-memoria-key")
        seen["body"] = json.loads(request.data)
        return Response()

    monkeypatch.setattr(server, "urlopen", fake_urlopen)
    server.ShellHandler._format_bdr(handler)

    assert captured["status"] == 200
    assert captured["payload"]["status"] == "ok"
    assert captured["payload"]["upstream"]["wal_preserved"] is True
    assert seen == {
        "url": "http://memoria/api/v1/admin/format",
        "method": "POST",
        "key": "internal-key",
        "body": {"confirm": "FORMATAR"},
    }
    assert handler.knowledge.calls == 1
    assert handler.trajectories.calls == 1
    assert handler.learner.reset_calls == 1
    assert handler.curiosity.actions == ["pause"]
    assert handler.curiosity.reset_calls == [True]
