# Resolutive DB Explorer

Status: experimental v0.1 scaffold

The Resolutive DB Explorer is a read-only visual and observability layer for BDR. Its first purpose is to make the resolutive address space observable without changing the stable database engine or depending on private internals.

Formal architecture and boundaries: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Design rules

1. **Do not modify the stable BDR v1 public contract merely for visualization.**
2. **Read through public APIs only.** The initial adapter uses `estatisticas()` and `entidades()`.
3. **Read-only first.** Administrative mutation, repair, migration and destructive actions are deliberately out of scope for v0.1.
4. **Visual semantics must correspond to real data.** The UI must not invent relationships or persistence state.
5. **Keep the module separable.** It lives inside the BDR repository during maturation but must remain technically separable.
6. **Prepare for Memoria.ia integration.** Semantic memory information must arrive through a distinct adapter/observation boundary.

## Visual model

The primary UI is a dark 2D navigable information universe with three functional zones:

- left: navigation, filters, layers/regions and future view selection;
- center: the Resolutive Universe canvas;
- right: technical inspector for the selected state.

Each currently observable BDR entity is rendered as a resolutive node:

- radial distance: normalized `rho_R`;
- angular position: `theta`;
- node scale: derived from `f_nu`;
- node details: `id`, `rho_R`, `phi`, `theta`, `f_nu`, payload size, bounded payload preview and fingerprint;
- global metrics: values returned by public `estatisticas()`.

No graph edge is drawn unless an actual relationship exists in a supplied observation contract.

## Architecture

```text
BDR public API
    |
    +--> ExplorerSnapshotProvider
    |
    +--> PublicBDRObservationProvider
    |
    v
Explorer observation boundary
    |
    +--> /api/health
    +--> /api/snapshot
    +--> /api/observation
    +--> /api/events
    |
    v
static browser UI
```

The web server uses Python's standard library in the first scaffold. This keeps the Explorer optional and avoids adding runtime dependencies to the BDR engine.

## Physical observation contract

`explorer/observation.py` defines `bdr-explorer-observation/v0.1`.

The contract uses capability discovery. A field is either:

- available through a documented/public BDR source; or
- explicitly unavailable, with a reason.

The Explorer must never infer operational durability from file names or parse private persistence structures merely to fill the UI.

Current public capabilities:

- record statistics;
- resolutive address-space data exposed by entities.

Currently unavailable pending a documented BDR telemetry contract:

- WAL state/bytes;
- checkpoint state;
- snapshot state;
- recovery state;
- disk usage;
- read/write latency telemetry.

This aligns with the existing BDR v1.x roadmap, which plans operational telemetry after the atomic persistence line.

## Event model

`explorer/events.py` defines a minimal transport-neutral `bdr-explorer-event/v0.1` model and bounded optional event buffer.

Initial vocabulary:

- `node.created`
- `node.updated`
- `node.accessed`
- `retrieval.started`
- `retrieval.candidate_found`
- `retrieval.node_selected`
- `retrieval.completed`
- `persistence.event`
- `checkpoint.event`
- `recovery.event`

The existence of an event type does not imply that BDR currently emits it. Producers must explicitly publish real events. This same boundary can later accept Memoria.ia-originated semantic/retrieval events.

## Two observation layers

### Physical BDR

Owned by BDR. Includes addresses, records and, when public telemetry exists, WAL/checkpoint/recovery/storage information.

### Semantic Memoria.ia

Owned by Memoria.ia. Future overlay may supply concepts, logical memories, relationships, candidates, selected trajectories, retrieval decisions, layers and temporal evolution.

The Explorer visual model can combine both layers while preserving their provenance.

## Run the demo

From the repository root:

```bash
python -m explorer.server --demo
```

Then open `http://127.0.0.1:8765`.

The demo creates a small in-memory BDR dataset and exposes it through the same read-only interfaces.

## Planned increments

### E01 — Read-only scaffold

- public-API snapshot adapter;
- health endpoint;
- visual shell and Resolutive Universe;
- entity inspection;
- physical observation capability contract;
- minimal event model;
- zero changes to BDR persistence/core.

### E02 — Persistent BDR connection

- define or consume an explicit safe inspection/opening contract;
- connect an existing BDR instance in read-only/inspection mode;
- never parse private WAL/snapshot internals directly from the UI.

### E03 — Operational observability

Consume the future public telemetry contract:

- WAL bytes;
- dirty mutations;
- checkpoint sequence/time;
- records/slots/index memory;
- durability mode;
- disk and recovery status.

### E04 — Memoria.ia visual overlay

Add a distinct Memoria.ia adapter for logical memories, occurrences, trajectories, semantic relations, retrieval decisions and layer/update-time information.

## Performance rule

Explorer instrumentation must be optional and measurable. Before enabling live instrumentation in the stable engine, benchmark BDR with observation disabled versus enabled for at least GET latency, PUT latency, throughput, CPU and memory overhead.

## Security rule

Payload previews are an experimental local convenience, not a future authorization model. The architecture must support disabling/redacting content and later enforcing authentication, organization isolation, roles and read-only/admin scopes.

## Boundary with the stable engine

Explorer code remains under `explorer/` plus its own tests/workflows. Any request for new engine observability must first become a documented backward-compatible BDR public contract before the Explorer relies on it.
