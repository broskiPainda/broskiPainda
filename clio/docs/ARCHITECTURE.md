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
  normalized event name, `db.py`), plus a ChromaDB semantic index
  (`semantic.py`) that catches near-duplicate names an exact match misses
  (e.g. "Cuban Missile Crisis" vs "The Cuban Missile Crisis of 1962"), so
  re-querying a similar scenario doesn't re-fetch and re-structure the same
  case. The semantic index is a best-effort layer — every method swallows
  its own failures and degrades to "no match," so the core cache never
  depends on it working. `CaseCache` also exposes `evict_stale()` /
  `evict_lru()` for bounding cache growth (see `scripts/evict_cache.py`).
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

## Hardening

- **Retry/backoff**: `app/sources/http.py`'s `RateLimitedClient` backs off
  exponentially on 429s from Wikipedia/Wikidata/UCDP, per their API
  etiquette. `app/engine/llm.py` wraps every Claude/z.ai call in a
  tenacity-based exponential backoff for transient connection/rate-limit/
  server errors (distinct from its own validation-failure retry loop, which
  re-prompts the model with the error rather than just resending).
- **Cache eviction**: see above — `CaseCache.evict_stale()` /
  `evict_lru()`, run via `scripts/evict_cache.py`.
- **Cost logging**: every `structured_call()` records its token usage
  against whichever `CostTracker` is active in the current async context
  (`app/engine/cost_tracking.py`, using `contextvars` so concurrent
  `asyncio.gather`'d calls attribute correctly). `pipeline.py` opens one
  tracker per analysis run, emits a final `cost_summary` SSE event, and
  persists the total via `CostLogStore` (`cost_logs` table), giving
  per-report token/cost visibility without instrumenting each step.
- **Retrieval-quality tests**: `tests/test_retrieval_quality.py` pins a
  Munich-1938-style appeasement scenario to a keyword-based check
  (`app/engine/retrieval_quality.py`) that nominated analogues include an
  appeasement-class case. The mocked variant always runs; a live variant
  against the real LLM is opt-in via `CLIO_LIVE_LLM_TESTS=1`.
