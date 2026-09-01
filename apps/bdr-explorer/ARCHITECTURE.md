# Resolutive DB Explorer Architecture

Status: experimental design contract for Explorer v0.1+

## System boundary

```text
BDR Core / persistence
        |
        | documented public contracts only
        v
BDR observation adapter
        |
        +-------------------+
        |                   |
        v                   v
physical observation     event boundary
        |                   |
        +---------+---------+
                  v
          Resolutive Visual Model
                  |
                  v
             Browser UI
                  ^
                  |
        Memoria.ia adapter (future)
```

Explorer is a consumer of BDR contracts, not a persistence subsystem.

## Provenance rule

Every visual datum carries an implicit or explicit source boundary:

- `bdr.public-api`: physical information supplied by BDR;
- `bdr.telemetry`: future operational telemetry supplied by BDR;
- `memoria.observation`: future semantic/retrieval information supplied by Memoria.ia;
- `ma2a.observation`: reserved future remote/federated observation source.

A visual relation must not be drawn merely because two nodes are spatially close.

## Current public physical model

The current stable Python surface permits observation of:

- entity identity;
- `rho_R`;
- `phi`;
- `theta`;
- `f_nu`;
- fingerprint;
- payload size/preview in the local experimental UI;
- aggregate statistics returned by `estatisticas()`.

The Explorer does not inspect private bucket objects.

## Persistence observability boundary

The repository already contains persistent WAL/snapshot/checkpoint/recovery implementations. Explorer must not obtain their state by parsing or mutating internal files.

Until a public contract exists, the following capabilities remain unavailable in the UI:

- WAL bytes/segments/state;
- latest durable sequence;
- checkpoint sequence/time;
- snapshot integrity/status;
- recovery result/status;
- disk footprint;
- durability mode;
- operational read/write latency.

This is capability absence, not a database failure.

## Event model

Events are observations, not commands. They may be delivered in-process first and transported over SSE/WebSocket only when live operation justifies it.

The v0.1 event envelope contains:

- schema version;
- kind;
- source;
- timestamp;
- data payload.

No event type grants permission to mutate BDR.

## Future Memoria.ia overlay

Memoria.ia should map its semantic objects to the shared visual model through a separate adapter. Expected future objects include:

- query/request;
- semantic candidates;
- selected memory;
- rejected candidates;
- logical relationships;
- retrieval trajectory;
- context result;
- layer/abstraction;
- memory hit/miss;
- mapping from logical memory to BDR record/address when available.

BDR remains the physical substrate; Memoria.ia remains the semantic owner.

## Security boundary

Explorer v0.1 binds locally by default and is read-only. Future deployments must be able to enforce:

- content redaction;
- authentication;
- organization isolation;
- role/scope separation;
- read-only vs administrative permissions;
- audit logging;
- future MA2A identity/certificates.

Raw payload visibility must never be assumed safe for remote/multi-tenant deployment.

## Performance budget and benchmark method

Before live instrumentation is introduced into stable BDR execution paths, measure two configurations using the same workload and environment:

A. Explorer/observation disabled

B. Explorer/observation enabled

Record at minimum:

- GET latency distribution;
- PUT latency distribution;
- operations/second;
- CPU time/utilization;
- process RSS / memory overhead;
- generated observation/event volume.

Initial acceptance target is not a fixed performance claim. The first gate is evidence: overhead must be quantified and regressions must be visible in CI before instrumentation becomes default.

Prefer sampling, bounded buffers and optional instrumentation over synchronous UI work in database critical paths.

## 2D-first visual architecture

The primary surface is an HTML/CSS/JavaScript 2D canvas/SVG universe. The data model remains independent of rendering coordinates so future WebGL/3D clients can consume the same observation contracts without changing BDR.

The initial projections are lenses over data, not storage semantics:

- resolutive address projection;
- future region/density projection;
- future persistence projection;
- future trajectory projection;
- future semantic Memoria.ia projection;
- future timeline/activity projection.

## Mutation policy

Explorer v0.1 exposes no destructive operation.

Future administrative actions must use explicit safe BDR APIs, authorization, confirmation and auditing. The visual graph must never directly rewrite WAL, snapshots, internal addresses or persistence files.
