"""Public-API adapter between BDR and the Resolutive DB Explorer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import bdr
from bdr import BancoDeDadosResolutivo, EntidadeResolutiva


class ExplorerSnapshotProvider:
    """Build serializable Explorer snapshots using public BDR APIs only."""

    def __init__(self, database: BancoDeDadosResolutivo) -> None:
        self.database = database

    @staticmethod
    def _payload_preview(payload: bytes, limit: int = 160) -> str:
        text = payload.decode("utf-8", errors="replace")
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    @classmethod
    def _entity_dict(cls, entity: EntidadeResolutiva) -> dict[str, Any]:
        return {
            "id": entity.id,
            "rho_R": entity.rho_R,
            "phi": entity.phi,
            "theta": entity.theta,
            "f_nu": entity.f_nu,
            "payload_size": len(entity.payload),
            "payload_preview": cls._payload_preview(entity.payload),
            "fingerprint": entity.fingerprint.hex(),
        }

    def snapshot(self) -> dict[str, Any]:
        stats = dict(self.database.estatisticas())
        nodes = [self._entity_dict(entity) for entity in self.database.entidades()]
        nodes.sort(key=lambda item: (item["rho_R"], item["phi"], item["id"]))
        return {
            "schema": "bdr-explorer-snapshot/v0.1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "bdr_version": bdr.__version__,
            "read_only": True,
            "statistics": stats,
            "nodes": nodes,
        }
