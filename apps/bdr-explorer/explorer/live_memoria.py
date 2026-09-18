"""Read-only temporal projection of persisted Memoria.ia episodes into BDR Explorer."""
from __future__ import annotations

import json
from urllib.request import Request, urlopen

from bdr import BancoDeDadosResolutivo

from .adapter import ExplorerSnapshotProvider
from .observation import PublicBDRObservationProvider


class LiveMemoriaSnapshotProvider:
    """Build bounded temporal Explorer views from the authoritative episode store.

    The Explorer never needs to materialize the whole database in the browser.
    It asks Memoria.ia for a contiguous temporal page and projects only that
    page into a transient Resolutive-DB view.
    """

    def __init__(self, memoria_url: str, api_key: str, *, default_limit: int = 900, max_limit: int = 1200) -> None:
        self.memoria_url = memoria_url.rstrip("/")
        self.api_key = api_key
        self.default_limit = max(1, int(default_limit))
        self.max_limit = max(self.default_limit, int(max_limit))

    def _json_get(self, path: str) -> dict[str, object]:
        request = Request(
            self.memoria_url + path,
            headers={"X-Memoria-Key": self.api_key},
            method="GET",
        )
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Memoria.ia returned invalid JSON object")
        return payload

    def page(self, *, offset: int = 0, limit: int | None = None) -> dict[str, object]:
        requested = self.default_limit if limit is None else int(limit)
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if requested < 1 or requested > self.max_limit:
            raise ValueError(f"limit must be between 1 and {self.max_limit}")
        payload = self._json_get(f"/api/v1/episodes/page?offset={offset}&limit={requested}")
        episodes = payload.get("episodes")
        if not isinstance(episodes, list):
            raise RuntimeError("Memoria.ia returned invalid episode page")
        return payload

    @staticmethod
    def _node_key(episode: dict[str, object], index: int) -> str:
        episode_id = str(episode.get("episode_id") or "")
        session_id = str(episode.get("session_id") or "")
        order = episode.get("order")
        if episode_id:
            return f"episode:{episode_id}"
        return f"episode:{session_id}:{order if order is not None else index}"

    @staticmethod
    def _node_payload(episode: dict[str, object]) -> str:
        role = str(episode.get("role") or "unknown")
        text = str(episode.get("text") or "")
        session_id = str(episode.get("session_id") or "")
        return f"[{role}] {text}\n.session={session_id}"

    @staticmethod
    def _episode_meta(episode: dict[str, object]) -> dict[str, object]:
        return {
            "episode_id": episode.get("episode_id"),
            "session_id": episode.get("session_id"),
            "role": episode.get("role"),
            "order": episode.get("order"),
            "timestamp": episode.get("timestamp"),
            "event_type": episode.get("event_type"),
            "topics_csv": episode.get("topics_csv"),
            "source_type": episode.get("source_type"),
            "source_authority": episode.get("source_authority"),
            "ultimate_source_memory_id": episode.get("ultimate_source_memory_id"),
            "superseded": episode.get("superseded"),
        }

    def snapshot(self, *, offset: int = 0, limit: int | None = None) -> dict[str, object]:
        page = self.page(offset=offset, limit=limit)
        episodes = [row for row in page.get("episodes", []) if isinstance(row, dict)]
        database = BancoDeDadosResolutivo(bucket_count=1 << 12)
        nodes: list[dict[str, object]] = []
        for index, episode in enumerate(episodes):
            entity = database.inserir(self._node_key(episode, offset + index), self._node_payload(episode))
            node = ExplorerSnapshotProvider._entity_dict(entity)
            node["temporal_index"] = offset + index
            node["episode"] = self._episode_meta(episode)
            nodes.append(node)
        nodes.sort(key=lambda item: (item["rho_R"], item["phi"], item["id"]))

        stats = dict(database.estatisticas())
        projected_records = int(stats.get("records", 0) or 0)
        total = int(page.get("total", 0) or 0)
        stats["projected_records"] = projected_records
        stats["visible_records"] = len(nodes)
        stats["records"] = total

        return {
            "schema": "bdr-explorer-snapshot/v0.2",
            "source": "memoria.ia-live",
            "read_only": True,
            "statistics": stats,
            "window": {
                "offset": int(page.get("offset", offset) or 0),
                "limit": int(page.get("limit", limit or self.default_limit) or self.default_limit),
                "returned": int(page.get("returned", len(episodes)) or 0),
                "total": total,
                "next_offset": page.get("next_offset"),
            },
            "nodes": nodes,
        }

    def observation(self) -> dict[str, object]:
        page = self.page(offset=0, limit=min(256, self.max_limit))
        database = BancoDeDadosResolutivo(bucket_count=1 << 12)
        for index, episode in enumerate(page.get("episodes", [])):
            if isinstance(episode, dict):
                database.inserir(self._node_key(episode, index), self._node_payload(episode))
        return PublicBDRObservationProvider(database).observe().as_dict()
