# CLIO — Historical Decision Intelligence

A political/military scenario goes in; verified historical analogues,
real base rates, and disciplined counterfactuals come out. No pre-curated
case base — every case is fetched from open sources at query time.

See `docs/ARCHITECTURE.md` for the pipeline, `docs/CASE_SCHEMA.md` for the
data contract, and `docs/MIGRATION_TO_KG.md` for the future graph-DB path.

## Status

All 5 build phases are in: Pydantic models, source clients (Wikipedia/
Wikidata/CoW/UCDP), the full 7-step analysis pipeline (structure → nominate
→ verify/enrich → similarity → base rates → counterfactuals → synthesis)
streamed over SSE, the React/Tailwind PWA frontend for all 4 pages, and
hardening (retry/backoff, cache eviction, per-report cost logging, a
retrieval-quality test suite).

## Setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY — never commit .env
python scripts/setup_data.py   # downloads Correlates of War CSVs into ../data/cow
pytest                          # all tests are offline (no network / no API key needed)
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

Or via Docker:

```bash
docker compose up --build
```

## Environment variables

Set in `backend/.env` (see `backend/.env.example`). Never hardcode secrets
in code or commit `.env`.

- `ANTHROPIC_API_KEY` — required. Works with a real Anthropic key, or a key
  from any Anthropic-compatible provider (see below).
- `ANTHROPIC_MODEL` — defaults to `claude-sonnet-4-6`.
- `CLIO_ANTHROPIC_BASE_URL` — optional. Set to point at an Anthropic-
  compatible endpoint instead of `api.anthropic.com` — e.g. z.ai's GLM
  models via `https://api.z.ai/api/anthropic` (pair with
  `ANTHROPIC_MODEL=glm-4.6`). Deliberately **not** named the more obvious
  `ANTHROPIC_BASE_URL`: several shells/CI environments set that generic name
  for unrelated tooling, and it would silently shadow this setting.
- `CLIO_CONTACT_EMAIL` — used in the descriptive User-Agent sent to
  Wikipedia/Wikidata per their API etiquette.

## Maintenance

- `python backend/scripts/setup_data.py` — one-time: download CoW datasets.
- `python backend/scripts/evict_cache.py` — periodic (e.g. cron): bounds the
  transient case cache by age and total size. See docstring for flags.
- Per-report LLM token/cost usage is logged to the `cost_logs` table
  (`app/cache/db.py::CostLogStore`) on every analysis run.

## Testing

`pytest` runs fully offline against mocked LLM/source clients — no network
or API key required, including a mocked end-to-end run of the naval-
blockade scenario and a Munich-1938-style appeasement retrieval-quality
check. A live retrieval-quality test against the real LLM is included but
skipped by default; run it with `CLIO_LIVE_LLM_TESTS=1 pytest
tests/test_retrieval_quality.py` in an environment with real network access
to your configured LLM endpoint.
