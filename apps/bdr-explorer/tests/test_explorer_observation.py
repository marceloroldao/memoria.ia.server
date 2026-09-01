from bdr import BancoDeDadosResolutivo
from explorer.events import EventBuffer, EventKind, ExplorerEvent
from explorer.observation import PublicBDRObservationProvider


def test_public_observation_exposes_only_supported_capabilities() -> None:
    db = BancoDeDadosResolutivo(bucket_count=32)
    db.inserir("alpha", "payload")

    observation = PublicBDRObservationProvider(db).observe().as_dict()

    assert observation["schema"] == "bdr-explorer-observation/v0.1"
    assert observation["read_only"] is True
    assert observation["values"]["statistics"]["records"] == 1
    assert observation["capabilities"]["records"]["available"] is True
    assert observation["capabilities"]["address_space"]["available"] is True

    for name in ("wal", "checkpoint", "snapshot", "recovery", "disk_usage"):
        capability = observation["capabilities"][name]
        assert capability["available"] is False
        assert capability["reason"]


def test_event_buffer_is_bounded_and_transport_neutral() -> None:
    buffer = EventBuffer(max_events=2)
    buffer.publish(ExplorerEvent.create(EventKind.NODE_CREATED, "test", node_id=1))
    buffer.publish(ExplorerEvent.create(EventKind.NODE_ACCESSED, "test", node_id=1))
    buffer.publish(ExplorerEvent.create(EventKind.NODE_SELECTED, "test", node_id=1))

    events = buffer.snapshot()

    assert len(events) == 2
    assert events[0]["kind"] == "node.accessed"
    assert events[1]["kind"] == "retrieval.node_selected"
    assert events[1]["data"] == {"node_id": 1}
    assert events[1]["schema"] == "bdr-explorer-event/v0.1"
