"""Read-only live projection of persisted Memoria.ia episodes into BDR Explorer."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

from bdr import BancoDeDadosResolutivo

from .adapter import ExplorerSnapshotProvider
from .observation import PublicBDRObservationProvider


class LiveMemoriaSnapshotProvider:
    """Build Explorer views from Memoria.ia's authoritative persisted episodes.

    This deliberately does not open Memoria.ia's native files directly while the
    runtime is writing them. Instead it consumes the read-only history contract
    exposed by Memoria.ia and materializes a transient BDR view for visualization.
    """

    def __init__(self, memoria_url: str, api_key: str, *, limit: int = 5000) -> None:
        self.memoria_url = memoria_url.rstrip("/")
        self.api_key = api_key
        self.limit = int(limit)

    def _episodes(self) -> list[dict[str, object]]:
        request = Request(
            f"{self.memoria_url}/api/v1/episodes/history?limit={self.limit}",
            headers={"X-Memoria-Key": self.api_key},
            method="GET",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        episodes = payload.get("episodes", [])
        if not isinstance(episodes, list):
            raise RuntimeError("Memoria.ia returned invalid episode history")
        return [row for row in episodes if isinstance(row, dict)]

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

    def database(self) -> BancoDeDadosResolutivo:
        database = BancoDeDadosResolutivo(bucket_count=1 << 12)
        rows = [
            (self._node_key(episode, index), self._node_payload(episode))
            for index, episode in enumerate(self._episodes())
        ]
        if rows:
            database.inserir_lote(rows)
        return database

    def snapshot(self) -> dict[str, object]:
        database = self.database()
        snapshot = ExplorerSnapshotProvider(database).snapshot()
        snapshot["source"] = "memoria.ia-live"
        snapshot["persisted_episodes"] = int(snapshot.get("statistics", {}).get("total_entidades", 0)) if isinstance(snapshot.get("statistics"), dict) else 0
        return snapshot

    def observation(self) -> dict[str, object]:
        return PublicBDRObservationProvider(self.database()).observe().as_dict()
