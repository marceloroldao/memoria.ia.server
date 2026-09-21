from pathlib import Path
import sys

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from config import ShellConfig
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
    assert capabilities["audit_log_v1"] is True
    assert capabilities["format_bdr"] is False
