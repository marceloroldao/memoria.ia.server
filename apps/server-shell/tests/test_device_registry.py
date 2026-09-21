from pathlib import Path
import json
import sys

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from device_registry import AuditLog, DeviceRegistry, DeviceRegistryError, ServerIdentity


def make_registry(tmp_path):
    identity = ServerIdentity(tmp_path)
    audit = AuditLog(tmp_path)
    return identity, audit, DeviceRegistry(tmp_path, identity, audit)


def payload(name="OFF.IA Teste"):
    return {
        "name": name,
        "type": "offia",
        "public_key": "ed25519:" + "a" * 64,
        "capabilities": {
            "cpu": "arm64",
            "gpu": "none",
            "ram_bytes": 8_000_000_000,
            "storage_bytes": 64_000_000_000,
            "models": ["local-small"],
        },
        "versions": {"offia": "0.1", "memoria": "v2", "bdr": "rc3"},
        "groups": ["family"],
        "permissions": ["memory.sync"],
    }


def test_server_identity_is_persistent(tmp_path):
    first = ServerIdentity(tmp_path).snapshot()
    second = ServerIdentity(tmp_path).snapshot()
    assert first["server_id"].startswith("srv-")
    assert first["server_id"] == second["server_id"]


def test_device_lifecycle_and_heartbeat(tmp_path):
    identity, audit, registry = make_registry(tmp_path)
    device, created = registry.register(payload(), actor="admin", client_ip="127.0.0.1")
    assert created is True
    assert device["server_id"] == identity.snapshot()["server_id"]
    assert device["status"] == "pending"
    assert device["certificate_status"] == "not_issued"

    active = registry.approve(device["device_id"], actor="admin")
    assert active["status"] == "active"

    alive = registry.heartbeat(
        device["device_id"],
        {"versions": {"offia": "0.2"}, "capabilities": {"cpu": "arm64", "models": ["local-medium"]}},
        actor="device-test",
    )
    assert alive["last_seen"]
    assert alive["versions"]["offia"] == "0.2"
    assert alive["capabilities"]["models"] == ["local-medium"]

    suspended = registry.suspend(device["device_id"], actor="admin")
    assert suspended["status"] == "suspended"

    resumed = registry.approve(device["device_id"], actor="admin")
    assert resumed["status"] == "active"

    revoked = registry.revoke(device["device_id"], actor="admin")
    assert revoked["status"] == "revoked"

    try:
        registry.heartbeat(device["device_id"], {}, actor="device-test")
    except DeviceRegistryError as exc:
        assert exc.status == 409
        assert exc.code == "device_not_active"
    else:
        raise AssertionError("revoked device heartbeat must be rejected")

    events = audit.recent(20)["events"]
    actions = [event["action"] for event in events]
    assert actions == [
        "device.register",
        "device.active",
        "device.heartbeat",
        "device.suspended",
        "device.active",
        "device.revoked",
    ]


def test_registration_is_idempotent_for_same_public_key(tmp_path):
    _identity, _audit, registry = make_registry(tmp_path)
    first, created_first = registry.register(payload(), actor="admin")
    second, created_second = registry.register(payload("Outro nome"), actor="admin")
    assert created_first is True
    assert created_second is False
    assert second["device_id"] == first["device_id"]
    assert registry.stats()["total"] == 1


def test_registry_persists_across_restart(tmp_path):
    identity, audit, registry = make_registry(tmp_path)
    device, _ = registry.register(payload(), actor="admin")
    registry.approve(device["device_id"], actor="admin")

    reopened = DeviceRegistry(tmp_path, ServerIdentity(tmp_path), AuditLog(tmp_path))
    loaded = reopened.get(device["device_id"])
    assert loaded["status"] == "active"
    assert reopened.stats()["active"] == 1


def test_audit_scrubs_secret_fields(tmp_path):
    audit = AuditLog(tmp_path)
    audit.append(
        "test.secret",
        actor="admin",
        details={"api_key": "should-not-leak", "nested": {"password": "also-secret"}, "safe": "ok"},
    )
    event = audit.recent(1)["events"][0]
    assert event["details"]["api_key"] == "[redacted]"
    assert event["details"]["nested"]["password"] == "[redacted]"
    assert event["details"]["safe"] == "ok"


def test_invalid_device_type_is_rejected(tmp_path):
    _identity, _audit, registry = make_registry(tmp_path)
    bad = payload()
    bad["type"] = "spaceship"
    try:
        registry.register(bad, actor="admin")
    except DeviceRegistryError as exc:
        assert exc.status == 422
        assert exc.code == "invalid_type"
    else:
        raise AssertionError("invalid type must fail")
