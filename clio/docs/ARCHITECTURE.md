# CLIO v1 Architecture

## Overview

CLIO is a Historical Decision Intelligence app. There is no pre-curated case
base: every historical case is fetched from open sources (Wikipedia,
Wikidata, Correlates of War, UCDP) at query time, structured by Claude, and
cached transiently. This keeps the system honest — every case a user sees
carries live source links, and nothing is hand-picked to make an analogy
look better than it is.

## Components

- **backend/app/models** — Pydantic schema contracts. `StructuredCase` is
  the load-bearing one: it's designed to migrate cleanly into a Neo4j graph
  later (see MIGRATION_TO_KG.md) without a breaking rewrite.
- **backend/app/sources** — typed clients for each open data source
  (`wikipedia.py`, `wikidata.py`, `cow.py`, `ucdp.py`), all going through a
  shared `RateLimitedClient` that sets a descriptive User-Agent and backs
  off politely on 429s.
- **backend/app/cache** — SQLite-backed structured-case cache (keyed by
  normalized event name) plus ChromaDB for semantic dedup, so re-querying a
  similar scenario doesn't re-fetch and re-structure the same cases.
- **backend/app/engine** — the 7-step analysis pipeline (see below).
- **backend/app/api** — FastAPI routes; Steps 2–7 stream over SSE so the
  frontend can show live per-analogue progress ("verifying X... dropped Y").
- **frontend** — React + Vite + Tailwind, mobile-first, installable PWA.

## Pipeline (7 steps)

1. **Structure** — Claude extracts actors, objectives, constraints, options,
   and the 12 structural dimensions from free text. User confirms/edits
   before anything else runs.
2. **Nominate** — Claude proposes 8–10 candidate analogues, including at
   least one deliberate negative analogue.
3. **Verify + enrich** — the hallucination firewall. Each candidate is
   checked against Wikipedia + Wikidata concurrently; anything that doesn't
   corroborate is dropped and logged. Survivors are structured into
   `StructuredCase` grounded only in fetched text, then cached.
4. **Similarity scoring** — weighted dimension overlap; top 5 + negative
   analogue kept, with matched/mismatched dimensions both surfaced.
5. **Base rates** — reference class built from CoW/UCDP filtered by the
   scenario's dimension values. Every number here comes from the datasets,
   never the LLM.
6. **Counterfactuals** — minimal-rewrite branches for the user's top 2
   options, grounded in the analogues' own counterfactuals.
7. **Synthesis** — final report: decision-quality (not outcome) verdicts,
   best-analogue deep dive, negative-analogue warning, base-rate table,
   counterfactual tree, red-team paragraph, confidence statement, and the
   standing disclaimer.

## Data flow guarantee

Narrative fields on a `StructuredCase` (summary, pre_event, decision,
execution_notes, outcomes) must be grounded in the fetched source text —
the structuring prompt forbids adding unsupported facts. Analytical fields
(assessments, counterfactuals, lessons) are Claude's reasoning, but must
reference sourced facts rather than invent new ones.
