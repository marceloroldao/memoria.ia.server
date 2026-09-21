from pathlib import Path
import json
import sys

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from raw_page_capture import RawPageCaptureStore, decode_web_bytes, inventory_resources


def test_raw_page_capture_is_byte_preserving_and_spooled_for_bit_analyze(tmp_path):
    body = (
        b"<!doctype html><html><head><title>x</title></head>"
        b"<body><nav>Menu principal</nav><img src='/a.png'>"
        b"<video poster='/poster.jpg'><source src='/movie.mp4'></video></body></html>"
    )
    text = decode_web_bytes(body, "text/html; charset=utf-8")
    resources = inventory_resources(text, "https://example.org/page")
    store = RawPageCaptureStore(tmp_path / "raw")
    result = store.capture(
        requested_url="https://example.org/page",
        final_url="https://example.org/page",
        content_type="text/html; charset=utf-8",
        body=body,
        resources=resources,
    )

    object_path = (tmp_path / "raw" / result["object_path"])
    assert object_path.read_bytes() == body
    assert result["bytes"] == len(body)
    assert result["resource_count"] == 3
    assert result["bit_analyze_status"] == "queued"

    manifest = json.loads((tmp_path / "raw" / result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["sha256"] == result["sha256"]
    assert {x["url"] for x in manifest["resources"]} == {
        "https://example.org/a.png",
        "https://example.org/poster.jpg",
        "https://example.org/movie.mp4",
    }

    rows = [
        json.loads(line)
        for line in (tmp_path / "raw" / "bit-analyze-ingest.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[-1]["source_id"] == result["source_id"]
    assert rows[-1]["byte_length"] == len(body)
    assert rows[-1]["object_path"] == result["object_path"]


def test_identical_bodies_share_content_address_but_keep_distinct_provenance(tmp_path):
    store = RawPageCaptureStore(tmp_path / "raw")
    first = store.capture(
        requested_url="https://a.example/page",
        final_url="https://a.example/page",
        content_type="text/plain",
        body=b"same bytes",
    )
    second = store.capture(
        requested_url="https://b.example/page",
        final_url="https://b.example/page",
        content_type="text/plain",
        body=b"same bytes",
    )
    assert first["sha256"] == second["sha256"]
    assert first["object_path"] == second["object_path"]
    assert first["capture_id"] != second["capture_id"]
    captures = (tmp_path / "raw" / "captures.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(captures) == 2
