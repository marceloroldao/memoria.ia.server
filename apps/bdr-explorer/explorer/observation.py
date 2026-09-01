"""Versioned observation contracts for the Resolutive DB Explorer.

This module deliberately does not inspect private WAL/snapshot structures. It
represents only capabilities that a BDR implementation explicitly exposes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


OBSERVATION_SCHEMA = "bdr-explorer-observation/v0.1"


@dataclass(frozen=True, slots=True)
class Capability:
    available: bool
    source: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class PhysicalObservation:
    schema: str
    generated_at: str
    read_only: bool
    capabilities: dict[str, Capability]
    values: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "generated_at": self.generated_at,
            "read_only": self.read_only,
            "capabilities": {name: asdict(cap) for name, cap in self.capabilities.items()},
            "values": self.values,
        }


class ObservationProvider(Protocol):
    def observe(self) -> PhysicalObservation: ...


class PublicBDRObservationProvider:
    """Observe only information available through the current public BDR API.

    Operational persistence telemetry is intentionally marked unavailable until
    BDR exposes a documented public telemetry contract.
    """

    def __init__(self, database: Any) -> None:
        self.database = database

    def observe(self) -> PhysicalObservation:
        stats = dict(self.database.estatisticas())
        public = Capability(True, "bdr.public-api")
        pending = Capability(
            False,
            "bdr.public-api",
            "requires a documented BDR operational telemetry contract",
        )
        capabilities = {
            "records": public,
            "address_space": public,
            "wal": pending,
            "checkpoint": pending,
            "snapshot": pending,
            "recovery": pending,
            "disk_usage": pending,
            "read_latency": pending,
            "write_latency": pending,
        }
        return PhysicalObservation(
            schema=OBSERVATION_SCHEMA,
            generated_at=datetime.now(timezone.utc).isoformat(),
            read_only=True,
            capabilities=capabilities,
            values={"statistics": stats},
        )
