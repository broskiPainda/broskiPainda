# Future Migration: SQLite/Chroma Cache → Neo4j Knowledge Graph

v1 deliberately ships without Neo4j — the SQLite cache + Chroma semantic
index is enough for a system that fetches everything at query time. This
doc sketches the migration path for a later version where cached cases
accumulate enough volume that a graph model pays for itself (cross-case
pattern queries, actor-centric traversal, dimension co-occurrence analysis).

## Why the current schema migrates cleanly

`StructuredCase` (backend/app/models/case.py) was designed as the contract:
nested objects map onto graph nodes/edges almost directly, which is why
field renames there are treated as breaking changes today.

## Target graph model (sketch)

Nodes:
- `(:Case {id, name, era, dates, summary, verified_against_sources})`
- `(:Actor {name, regime_type})`
- `(:Outcome {horizon, description, valence})`
- `(:Dimension {key})` — one node per of the 12 dimension keys
- `(:Source {url})`

Relationships:
- `(:Case)-[:INVOLVES {role}]->(:Actor)`
- `(:Case)-[:RESULTED_IN]->(:Outcome)`
- `(:Case)-[:HAS_DIMENSION_VALUE {value}]->(:Dimension)`
- `(:Case)-[:SOURCED_FROM]->(:Source)`
- `(:Case)-[:ANALOGOUS_TO {similarity_score, matched_dimensions}]->(:Case)`
  — populated retroactively from historical similarity-scoring runs (Step 4
  results), turning one-off comparisons into a persistent analogy graph.

## Loader sketch

A `kg_loader.py` script would:

1. Read all rows from the SQLite case cache.
2. For each `StructuredCase`, upsert `Case`, `Actor`, `Outcome`, `Source`
   nodes and their relationships (idempotent on `Case.id` / `Actor.name` /
   `Source.url`).
3. Upsert `HAS_DIMENSION_VALUE` edges from `CaseDimensions`.
4. Backfill `ANALOGOUS_TO` edges from any `Report.matched_cases` records
   persisted in scenario history, so accumulated analysis runs become graph
   structure rather than being discarded after each report.

## What does NOT change

- `StructuredCase` and the `Dimension` enum stay the schema of record; the
  loader reads from them, it doesn't reshape them.
- The verification/grounding pipeline (Step 3) stays identical — the graph
  is a downstream projection of the same cached, source-grounded cases, not
  a new source of truth.
- v1's transient-cache guarantee (cases are machine-generated, not curated,
  always source-linked) carries over: the KG is additive indexing, not a
  hand-curated case base.

## Trigger for doing this

Not before the case cache has enough volume that repeated Step 3/4 work
across scenarios is measurably wasteful, or a feature genuinely needs graph
traversal (e.g. "show me all cases where a third party escalated after
initially staying neutral") that dimension-overlap scoring can't express.
