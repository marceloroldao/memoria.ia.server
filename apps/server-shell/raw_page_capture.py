"""Lossless public-web capture for later structural analysis.

The capture layer does not decide which page regions are meaningful. Accepted
HTTP bodies are stored byte-for-byte and referenced by SHA-256. Human-readable
text/excerpts are derived views only; bit.analyze can consume the original bytes
later through the append-only ingest spool.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import re
from threading import Lock
import uuid
from urllib.parse import urljoin, urlparse


_CHARSET_RE = re.compile(r"charset\s*=\s*['\"]?([^;\s'\"]+)", re.I)
_RESOURCE_ATTRS = {
    "img": ("src",),
    "video": ("src", "poster"),
    "audio": ("src",),
    "source": ("src",),
    "track": ("src",),
    "iframe": ("src",),
    "embed": ("src",),
    "object": ("data",),
    "script": ("src",),
    "link": ("href",),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def decode_web_bytes(body: bytes, content_type: str) -> str:
    match = _CHARSET_RE.search(content_type or "")
    charset = match.group(1) if match else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


class _ResourceInventory(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=False)
        self.base_url = base_url
        self.resources: list[dict[str, str]] = []
        self._seen: set[tuple[str, str, str]] = set()

    def _offer(self, tag: str, attr: str, value: str) -> None:
        value = (value or "").strip()
        if not value or value.startswith(("data:", "javascript:", "mailto:", "tel:", "#")):
            return
        absolute = urljoin(self.base_url, value)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return
        key = (tag, attr, absolute)
        if key in self._seen:
            return
        self._seen.add(key)
        self.resources.append({"tag": tag, "attribute": attr, "url": absolute})

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        values = {str(k).casefold(): str(v or "") for k, v in attrs}
        for attr in _RESOURCE_ATTRS.get(tag, ()):
            self._offer(tag, attr, values.get(attr, ""))
        if tag in {"img", "source"} and values.get("srcset"):
            for candidate in values["srcset"].split(","):
                url = candidate.strip().split(" ", 1)[0]
                self._offer(tag, "srcset", url)


def inventory_resources(html: str, base_url: str) -> list[dict[str, str]]:
    parser = _ResourceInventory(base_url)
    parser.feed(html)
    return parser.resources


class RawPageCaptureStore:
    """Content-addressed raw bodies plus append-only provenance/spool records."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.objects = self.root / "objects" / "sha256"
        self.manifests = self.root / "manifests"
        self.captures_file = self.root / "captures.jsonl"
        self.bit_analyze_spool = self.root / "bit-analyze-ingest.jsonl"
        self._lock = Lock()

    def capture(
        self,
        *,
        requested_url: str,
        final_url: str,
        content_type: str,
        body: bytes,
        resources: list[dict[str, str]] | None = None,
    ) -> dict[str, object]:
        digest = hashlib.sha256(body).hexdigest()
        capture_id = f"web:{uuid.uuid4().hex}"
        object_rel = Path("objects") / "sha256" / digest[:2] / f"{digest}.bin"
        object_path = self.root / object_rel
        manifest_rel = Path("manifests") / f"{capture_id.replace(':', '-')}.json"
        manifest_path = self.root / manifest_rel
        observed_at = _now()
        resource_rows = list(resources or [])
        manifest = {
            "schema": "memoria-raw-web-capture/v1",
            "capture_id": capture_id,
            "source_id": f"raw-web:sha256:{digest}",
            "observed_at": observed_at,
            "requested_url": requested_url,
            "final_url": final_url,
            "content_type": content_type,
            "bytes": len(body),
            "sha256": digest,
            "object_path": object_rel.as_posix(),
            "resource_count": len(resource_rows),
            "resources": resource_rows,
        }
        spool = {
            "schema": "bit-analyze-ingest/v1",
            "source_id": manifest["source_id"],
            "capture_id": capture_id,
            "observed_at": observed_at,
            "byte_offset": 0,
            "byte_length": len(body),
            "sha256": digest,
            "content_type": content_type,
            "url": final_url,
            "object_path": object_rel.as_posix(),
            "provenance": {
                "kind": "public_web_response",
                "requested_url": requested_url,
                "final_url": final_url,
            },
        }

        with self._lock:
            object_path.parent.mkdir(parents=True, exist_ok=True)
            self.manifests.mkdir(parents=True, exist_ok=True)
            if not object_path.exists():
                tmp = object_path.with_suffix(".tmp")
                tmp.write_bytes(body)
                os.replace(tmp, object_path)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            with self.captures_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({k: v for k, v in manifest.items() if k != "resources"}, ensure_ascii=False) + "\n")
            with self.bit_analyze_spool.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(spool, ensure_ascii=False) + "\n")

        return {
            "capture_id": capture_id,
            "source_id": manifest["source_id"],
            "sha256": digest,
            "bytes": len(body),
            "content_type": content_type,
            "object_path": object_rel.as_posix(),
            "manifest_path": manifest_rel.as_posix(),
            "resource_count": len(resource_rows),
            "bit_analyze_status": "queued",
        }
