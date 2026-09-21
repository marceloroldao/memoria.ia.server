from pathlib import Path
import base64
import json
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from device_auth import DeviceAuthManager, DeviceAuthority
from device_registry import AuditLog, DeviceRegistry, DeviceRegistryError, ServerIdentity


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def make_stack(tmp_path):
    identity = ServerIdentity(tmp_path)
    audit = AuditLog(tmp_path)
    registry = DeviceRegistry(tmp_path, identity, audit)
    authority = DeviceAuthority(tmp_path, identity, audit)
    registry.set_certificate_issuer(authority.issue_certificate)
    auth = DeviceAuthManager(registry, authority, audit, challenge_seconds=60, token_seconds=600)
    return identity, audit, registry, authority, auth


def device_key():
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, "ed25519:" + b64url(raw)


def register_active(registry, public_key):
    device, created = registry.register(
        {
            "name": "OFF.IA Auth",
            "type": "offia",
            "public_key": public_key,
            "capabilities": {"cpu": "arm64", "models": ["local-small"]},
            "versions": {"offia": "0.1"},
            "groups": [],
            "permissions": ["memory.sync", "heartbeat"],
        },
        actor="admin",
    )
    assert created is True
    return registry.approve(device["device_id"], actor="admin")


def test_authority_persists_same_signing_identity(tmp_path):
    identity = ServerIdentity(tmp_path)
    audit = AuditLog(tmp_path)
    first = DeviceAuthority(tmp_path, identity, audit).public_snapshot()
    second = DeviceAuthority(tmp_path, identity, audit).public_snapshot()
    assert first["server_id"] == identity.snapshot()["server_id"]
    assert first["public_key"] == second["public_key"]
    assert first["public_key_fingerprint"] == second["public_key_fingerprint"]


def test_approval_issues_server_certificate_for_ed25519_device(tmp_path):
    _identity, audit, registry, authority, _auth = make_stack(tmp_path)
    _private, public_key = device_key()
    device = register_active(registry, public_key)

    assert device["status"] == "active"
    assert device["certificate_status"] == "active"
    assert authority.verify_certificate(device["certificate"]) is True
    assert device["certificate"]["payload"]["device_id"] == device["device_id"]
    assert device["certificate"]["payload"]["public_key_fingerprint"] == device["public_key_fingerprint"]

    actions = [event["action"] for event in audit.recent(20)["events"]]
    assert "device.certificate_issued" in actions


def test_challenge_signature_token_and_authenticated_heartbeat(tmp_path):
    _identity, _audit, registry, _authority, auth = make_stack(tmp_path)
    private, public_key = device_key()
    device = register_active(registry, public_key)

    challenge = auth.challenge(device["device_id"], client_ip="127.0.0.1")
    signature = private.sign(challenge["signing_message"].encode("utf-8"))
    token = auth.verify(
        device["device_id"],
        challenge["challenge_id"],
        b64url(signature),
        client_ip="127.0.0.1",
    )

    assert token["token_type"] == "Device"
    assert auth.authenticate("Device " + token["token"]) == device["device_id"]

    authenticated_id = auth.authenticate("Device " + token["token"])
    heartbeat = registry.heartbeat(
        authenticated_id,
        {"versions": {"offia": "0.2"}, "capabilities": {"cpu": "arm64", "models": ["local-medium"]}},
        actor=f"device:{authenticated_id}",
    )
    assert heartbeat["last_seen"]
    assert heartbeat["versions"]["offia"] == "0.2"


def test_challenge_is_one_time_even_after_bad_signature(tmp_path):
    _identity, audit, registry, _authority, auth = make_stack(tmp_path)
    private, public_key = device_key()
    other_private = Ed25519PrivateKey.generate()
    device = register_active(registry, public_key)

    challenge = auth.challenge(device["device_id"])
    bad = other_private.sign(challenge["signing_message"].encode("utf-8"))
    try:
        auth.verify(device["device_id"], challenge["challenge_id"], b64url(bad))
    except DeviceRegistryError as exc:
        assert exc.status == 401
        assert exc.code == "signature_invalid"
    else:
        raise AssertionError("invalid signature must fail")

    good = private.sign(challenge["signing_message"].encode("utf-8"))
    try:
        auth.verify(device["device_id"], challenge["challenge_id"], b64url(good))
    except DeviceRegistryError as exc:
        assert exc.code == "challenge_invalid"
    else:
        raise AssertionError("consumed challenge must never be replayable")

    assert [e["action"] for e in audit.recent(20)["events"]].count("device.auth_failed") >= 2


def test_suspend_and_revoke_immediately_invalidate_device_token(tmp_path):
    _identity, _audit, registry, _authority, auth = make_stack(tmp_path)
    private, public_key = device_key()
    device = register_active(registry, public_key)

    challenge = auth.challenge(device["device_id"])
    signature = private.sign(challenge["signing_message"].encode("utf-8"))
    token = auth.verify(device["device_id"], challenge["challenge_id"], b64url(signature))["token"]
    assert auth.authenticate("Device " + token) == device["device_id"]

    suspended = registry.suspend(device["device_id"], actor="admin")
    assert suspended["certificate_status"] == "suspended"
    try:
        auth.authenticate("Device " + token)
    except DeviceRegistryError as exc:
        assert exc.status == 403
        assert exc.code == "device_not_active"
    else:
        raise AssertionError("suspended device token must be rejected")

    active = registry.approve(device["device_id"], actor="admin")
    assert active["certificate_status"] == "active"
    challenge2 = auth.challenge(device["device_id"])
    signature2 = private.sign(challenge2["signing_message"].encode("utf-8"))
    token2 = auth.verify(device["device_id"], challenge2["challenge_id"], b64url(signature2))["token"]

    revoked = registry.revoke(device["device_id"], actor="admin")
    assert revoked["certificate_status"] == "revoked"
    try:
        auth.authenticate("Device " + token2)
    except DeviceRegistryError as exc:
        assert exc.status == 403
    else:
        raise AssertionError("revoked device token must be rejected")


def test_non_ed25519_legacy_device_can_be_active_but_cannot_authenticate(tmp_path):
    _identity, _audit, registry, _authority, auth = make_stack(tmp_path)
    device, _ = registry.register(
        {
            "name": "Legacy",
            "type": "computer",
            "public_key": "legacy-public-key-material",
            "capabilities": {},
            "versions": {},
            "groups": [],
            "permissions": [],
        },
        actor="admin",
    )
    active = registry.approve(device["device_id"], actor="admin")
    assert active["status"] == "active"
    assert active["certificate_status"] == "not_issued"
    try:
        auth.challenge(device["device_id"])
    except DeviceRegistryError as exc:
        assert exc.status == 403
        assert exc.code == "certificate_not_active"
    else:
        raise AssertionError("legacy key without certificate must not authenticate")


def test_corrupt_authority_fails_closed(tmp_path):
    identity = ServerIdentity(tmp_path)
    audit = AuditLog(tmp_path)
    DeviceAuthority(tmp_path, identity, audit)
    path = tmp_path / "device-authority.json"
    payload = json.loads(path.read_text("utf-8"))
    payload["private_key"] = "broken"
    path.write_text(json.dumps(payload), encoding="utf-8")

    try:
        DeviceAuthority(tmp_path, identity, audit)
    except RuntimeError:
        pass
    else:
        raise AssertionError("corrupt authority must not silently rotate server key")


def test_corrupt_registry_and_identity_fail_closed(tmp_path):
    identity = ServerIdentity(tmp_path)
    audit = AuditLog(tmp_path)
    registry = DeviceRegistry(tmp_path, identity, audit)
    _private, public_key = device_key()
    registry.register(
        {"name":"node","type":"iot","public_key":public_key,"capabilities":{},"versions":{},"groups":[],"permissions":[]},
        actor="admin",
    )
    (tmp_path / "devices.json").write_text("{not-json", encoding="utf-8")
    try:
        DeviceRegistry(tmp_path, identity, audit)
    except RuntimeError:
        pass
    else:
        raise AssertionError("corrupt registry must fail closed")

    (tmp_path / "server-identity.json").write_text("{not-json", encoding="utf-8")
    try:
        ServerIdentity(tmp_path)
    except RuntimeError:
        pass
    else:
        raise AssertionError("corrupt server identity must fail closed")



def test_challenge_rate_limit_is_bounded_to_known_device(tmp_path):
    _identity, _audit, registry, _authority, auth = make_stack(tmp_path)
    private, public_key = device_key()
    device = register_active(registry, public_key)

    for _ in range(20):
        auth.challenge(device["device_id"], client_ip="10.0.0.10")
    try:
        auth.challenge(device["device_id"], client_ip="10.0.0.10")
    except DeviceRegistryError as exc:
        assert exc.status == 429
        assert exc.code == "challenge_rate_limited"
    else:
        raise AssertionError("challenge rate limit must activate")

    before = len(auth._challenge_rate)
    try:
        auth.challenge("dev-" + "f" * 32, client_ip="10.0.0.11")
    except DeviceRegistryError as exc:
        assert exc.status == 404
    else:
        raise AssertionError("unknown device challenge must fail")
    assert len(auth._challenge_rate) == before



def test_permission_change_reissues_certificate_and_denies_removed_scope(tmp_path):
    _identity, audit, registry, authority, auth = make_stack(tmp_path)
    private, public_key = device_key()
    device = register_active(registry, public_key)

    challenge = auth.challenge(device["device_id"])
    signature = private.sign(challenge["signing_message"].encode("utf-8"))
    token = auth.verify(device["device_id"], challenge["challenge_id"], b64url(signature))["token"]

    assert auth.authenticate(
        "Device " + token,
        required_permission="device.heartbeat",
    ) == device["device_id"]

    old_serial = registry.get(device["device_id"])["certificate"]["payload"]["serial"]
    updated = registry.set_permissions(
        device["device_id"],
        ["device.self.read"],
        actor="admin",
    )
    new_serial = updated["certificate"]["payload"]["serial"]
    assert new_serial != old_serial
    assert updated["permissions"] == ["device.self.read"]
    assert authority.verify_device_certificate(updated["certificate"], updated) is True

    assert auth.authenticate(
        "Device " + token,
        required_permission="device.self.read",
    ) == device["device_id"]

    try:
        auth.authenticate(
            "Device " + token,
            required_permission="device.heartbeat",
            client_ip="127.0.0.1",
        )
    except DeviceRegistryError as exc:
        assert exc.status == 403
        assert exc.code == "device_permission_denied"
    else:
        raise AssertionError("removed scope must be denied")

    events = audit.recent(20)["events"]
    assert any(event["action"] == "device.permission_denied" for event in events)
