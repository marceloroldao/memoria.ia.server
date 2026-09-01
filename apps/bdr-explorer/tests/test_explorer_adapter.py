from bdr import BancoDeDadosResolutivo
from explorer.adapter import ExplorerSnapshotProvider


def test_snapshot_uses_public_entity_data() -> None:
    db = BancoDeDadosResolutivo(bucket_count=32)
    entity = db.inserir("alpha", "payload alpha")

    snapshot = ExplorerSnapshotProvider(db).snapshot()

    assert snapshot["schema"] == "bdr-explorer-snapshot/v0.1"
    assert snapshot["read_only"] is True
    assert snapshot["statistics"]["records"] == 1
    assert len(snapshot["nodes"]) == 1

    node = snapshot["nodes"][0]
    assert node["id"] == entity.id
    assert node["rho_R"] == entity.rho_R
    assert node["phi"] == entity.phi
    assert node["theta"] == entity.theta
    assert node["f_nu"] == entity.f_nu
    assert node["payload_size"] == len(entity.payload)
    assert node["payload_preview"] == "payload alpha"
    assert node["fingerprint"] == entity.fingerprint.hex()


def test_snapshot_payload_preview_is_bounded() -> None:
    db = BancoDeDadosResolutivo(bucket_count=32)
    db.inserir("long", "x" * 300)

    node = ExplorerSnapshotProvider(db).snapshot()["nodes"][0]

    assert len(node["payload_preview"]) == 160
    assert node["payload_preview"].endswith("…")
    assert node["payload_size"] == 300
