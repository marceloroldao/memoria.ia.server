from pathlib import Path
import base64
import json
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from device_auth import DeviceAuthority
from device_enrollment import DeviceEnrollmentManager
from device_registry import AuditLog, DeviceRegistry, DeviceRegistryError, ServerIdentity


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def keypair():
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, "ed25519:" + b64url(raw)


def make_manager(tmp_path):
    identity = ServerIdentity(tmp_path)
    audit = AuditLog(tmp_path)
    registry = DeviceRegistry(tmp_path, identity, audit)
    authority = DeviceAuthority(tmp_path, identity, audit)
    registry.set_certificate_issuer(authority.issue_certificate)
    manager = DeviceEnrollmentManager(tmp_path, identity, registry, audit)
    return identity, audit, registry, authority, manager


def test_invitation_secret_is_returned_once_and_not_persisted_plaintext(tmp_path):
    _identity, _audit, _registry, _authority, manager = make_manager(tmp_path)
    created = manager.create(
        {
            "label": "OFF.IA cliente 1",
            "type": "offia",
            "permissions": ["device.self.read", "device.heartbeat", "memory.sync"],
            "expires_minutes": 30,
        },
        actor="admin",
    )
    code = created["enrollment_code"]
    assert code.startswith("enr1_")
    assert created["invitation"]["status"] == "active"
    assert "code_hash" not in created["invitation"]

    persisted = (tmp_path / "enrollments.json").read_text("utf-8")
    assert code not in persisted
    listed = manager.list()["invitations"][0]
    assert "code_hash" not in listed
    assert "enrollment_code" not in listed


def test_claim_creates_pending_device_with_invitation_scopes(tmp_path):
    identity, audit, registry, _authority, manager = make_manager(tmp_path)
    _private, public_key = keypair()
    created = manager.create(
        {
            "label": "OFF.IA cliente 2",
            "type": "offia",
            "permissions": ["device.self.read", "device.heartbeat", "memory.sync"],
            "groups": ["customer-2"],
            "expires_minutes": 30,
        },
        actor="admin",
    )

    claimed = manager.claim(
        {
            "enrollment_code": created["enrollment_code"],
            "name": "OFF.IA do cliente",
            "public_key": public_key,
            "capabilities": {"cpu": "arm64", "models": ["local-small"]},
            "versions": {"offia": "0.1"},
        },
        client_ip="127.0.0.1",
    )

    device = claimed["device"]
    assert claimed["status"] == "pending_approval"
    assert device["server_id"] == identity.snapshot()["server_id"]
    assert device["status"] == "pending"
    assert device["type"] == "offia"
    assert device["groups"] == ["customer-2"]
    assert device["permissions"] == ["device.self.read", "device.heartbeat", "memory.sync"]

    invitation = manager.list()["invitations"][0]
    assert invitation["status"] == "consumed"
    assert invitation["device_id"] == device["device_id"]
    assert registry.get(device["device_id"])["public_key"] == public_key

    actions = [event["action"] for event in audit.recent(20)["events"]]
    assert "enrollment.created" in actions
    assert "enrollment.claimed" in actions


def test_consumed_invitation_cannot_be_replayed(tmp_path):
    _identity, _audit, _registry, _authority, manager = make_manager(tmp_path)
    _private, public_key = keypair()
    created = manager.create({"type": "offia"}, actor="admin")
    payload = {
        "enrollment_code": created["enrollment_code"],
        "name": "Primeiro",
        "public_key": public_key,
    }
    manager.claim(payload, client_ip="127.0.0.1")

    _private2, public_key2 = keypair()
    payload["name"] = "Segundo"
    payload["public_key"] = public_key2
    try:
        manager.claim(payload, client_ip="127.0.0.1")
    except DeviceRegistryError as exc:
        assert exc.status == 409
        assert exc.code == "enrollment_consumed"
    else:
        raise AssertionError("enrollment invitation must be one-time")


def test_existing_device_key_does_not_consume_new_invitation(tmp_path):
    _identity, _audit, registry, _authority, manager = make_manager(tmp_path)
    _private, public_key = keypair()
    existing, _ = registry.register(
        {
            "name": "Já cadastrado",
            "type": "offia",
            "public_key": public_key,
            "permissions": ["device.self.read", "device.heartbeat"],
        },
        actor="admin",
    )
    created = manager.create({"type": "offia"}, actor="admin")
    try:
        manager.claim(
            {
                "enrollment_code": created["enrollment_code"],
                "name": "Reuso",
                "public_key": public_key,
            }
        )
    except DeviceRegistryError as exc:
        assert exc.status == 409
        assert exc.code == "device_already_registered"
    else:
        raise AssertionError("existing key must not consume a new invite")

    invitation = manager.list()["invitations"][0]
    assert invitation["status"] == "active"
    assert registry.get(existing["device_id"])["name"] == "Já cadastrado"


def test_revoked_invitation_cannot_be_claimed(tmp_path):
    _identity, _audit, _registry, _authority, manager = make_manager(tmp_path)
    _private, public_key = keypair()
    created = manager.create({"type": "offia"}, actor="admin")
    enrollment_id = created["invitation"]["enrollment_id"]
    revoked = manager.revoke(enrollment_id, actor="admin")
    assert revoked["status"] == "revoked"

    try:
        manager.claim(
            {
                "enrollment_code": created["enrollment_code"],
                "name": "Bloqueado",
                "public_key": public_key,
            }
        )
    except DeviceRegistryError as exc:
        assert exc.status == 403
        assert exc.code == "enrollment_revoked"
    else:
        raise AssertionError("revoked invite must fail")


def test_corrupt_enrollment_state_fails_closed(tmp_path):
    _identity, _audit, _registry, _authority, manager = make_manager(tmp_path)
    manager.create({"type": "offia"}, actor="admin")
    (tmp_path / "enrollments.json").write_text("{broken", encoding="utf-8")
    try:
        DeviceEnrollmentManager(
            tmp_path,
            ServerIdentity(tmp_path),
            DeviceRegistry(tmp_path, ServerIdentity(tmp_path), AuditLog(tmp_path)),
            AuditLog(tmp_path),
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("corrupt enrollment state must fail closed")
