from explorer.live_memoria import LiveMemoriaSnapshotProvider


def test_temporal_snapshot_can_project_records_beyond_5000(monkeypatch):
    provider = LiveMemoriaSnapshotProvider("http://memoria", "secret", default_limit=900, max_limit=1200)

    def fake_page(*, offset=0, limit=None):
        assert offset == 5000
        assert limit == 2
        return {
            "schema": "memoria-episode-page/v1",
            "offset": 5000,
            "limit": 2,
            "returned": 2,
            "total": 20000,
            "next_offset": 5002,
            "episodes": [
                {
                    "episode_id": "ep-5001",
                    "session_id": "raw",
                    "role": "user",
                    "text": "<html>raw one</html>",
                    "order": 5001,
                    "timestamp": "2026-09-18T19:00:00Z",
                    "event_type": "raw",
                    "topics_csv": "",
                    "source_type": "user_assertion",
                    "source_authority": 0.95,
                    "ultimate_source_memory_id": "ep-5001",
                    "superseded": False,
                },
                {
                    "episode_id": "ep-5002",
                    "session_id": "raw",
                    "role": "user",
                    "text": "<html>raw two</html>",
                    "order": 5002,
                    "timestamp": "2026-09-18T19:00:01Z",
                    "event_type": "raw",
                    "topics_csv": "",
                    "source_type": "user_assertion",
                    "source_authority": 0.95,
                    "ultimate_source_memory_id": "ep-5002",
                    "superseded": False,
                },
            ],
        }

    monkeypatch.setattr(provider, "page", fake_page)
    snapshot = provider.snapshot(offset=5000, limit=2)

    assert snapshot["schema"] == "bdr-explorer-snapshot/v0.2"
    assert snapshot["statistics"]["records"] == 20000
    assert snapshot["statistics"]["projected_records"] == 2
    assert snapshot["statistics"]["visible_records"] == 2
    assert snapshot["window"]["offset"] == 5000
    assert snapshot["window"]["total"] == 20000
    assert sorted(node["temporal_index"] for node in snapshot["nodes"]) == [5000, 5001]
    assert {node["episode"]["episode_id"] for node in snapshot["nodes"]} == {"ep-5001", "ep-5002"}


def test_temporal_provider_bounds_page_size():
    provider = LiveMemoriaSnapshotProvider("http://memoria", "secret", default_limit=900, max_limit=1200)
    try:
        provider.page(offset=0, limit=1201)
    except ValueError as exc:
        assert "1200" in str(exc)
    else:
        raise AssertionError("page size above rendering bound must fail before network access")
