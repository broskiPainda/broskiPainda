# CLIO — Historical Decision Intelligence

A political/military scenario goes in; verified historical analogues,
real base rates, and disciplined counterfactuals come out. No pre-curated
case base — every case is fetched from open sources at query time.

See `docs/ARCHITECTURE.md` for the pipeline, `docs/CASE_SCHEMA.md` for the
data contract, and `docs/MIGRATION_TO_KG.md` for the future graph-DB path.

## Status

Phase 1 (this commit): repo scaffold, Pydantic models, CoW data setup
script, source clients (Wikipedia/Wikidata/CoW/UCDP) with unit tests, and a
FastAPI skeleton with a `/api/health` check. The analysis pipeline
(Steps 1–7) and full frontend land in later phases.

## Setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY — never commit .env
python scripts/setup_data.py   # downloads Correlates of War CSVs into ../data/cow
pytest                          # 24 tests, all offline (no network / no API key needed)
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

Set in `backend/.env` (see `backend/.env.example`). Required for the
pipeline (Phase 2+): `ANTHROPIC_API_KEY`. Never hardcode secrets in code or
commit `.env`.
