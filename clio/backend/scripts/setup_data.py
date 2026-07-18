#!/usr/bin/env python3
"""Download Correlates of War (CoW) CSV datasets and load them into SQLite.

Run once before starting the backend:

    python backend/scripts/setup_data.py

Datasets used:
  - MIDA 5.0 (dispute-level Militarized Interstate Disputes — one row per
    dispute, with start/end year, hostility level, and outcome)
  - National Material Capabilities (NMC), abridged — country-year CINC scores
  - A CoW war dataset (Inter-State War v4.0 preferred; Intra-State War v5.1
    also loads, since the column layout is close enough — see load_wars).
    Note: this table isn't currently queried by the base-rate step (Step 5
    uses `mids` only) — it's loaded for future use.

Source: https://correlatesofwar.org/data-sets/

correlatesofwar.org doesn't reliably serve its intermediate certificate
chain, so this script's own download often fails with a "certificate verify
failed" error even with valid local CA certs (browsers work around this via
AIA chasing; Python's ssl module doesn't). If that happens: download the
datasets by hand from the URL above and drop the CSVs directly at
data/cow/mids.csv, data/cow/wars.csv, data/cow/capabilities.csv — this
script checks for those first, before attempting any network call.
"""
from __future__ import annotations

import csv
import io
import sqlite3
import sys
import zipfile
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402

DATASETS = {
    "mids": {
        "url": "https://correlatesofwar.org/wp-content/uploads/MIDs-5.0.zip",
        "csv_hint": "MIDA",  # dispute-level file within the zip
    },
    "wars": {
        "url": "https://correlatesofwar.org/wp-content/uploads/Inter-StateWarData_v4.0.zip",
        "csv_hint": "Inter-State",
    },
    "capabilities": {
        "url": "https://correlatesofwar.org/wp-content/uploads/NMC-70-abridged.zip",
        "csv_hint": "NMC",
    },
}


def download_zip(url: str, dest_dir: Path, timeout: float = 60.0) -> bytes | None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(
            timeout=timeout,
            headers={"User-Agent": get_settings().user_agent},
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content
    except httpx.HTTPError as exc:
        print(f"  WARNING: failed to download {url}: {exc}", file=sys.stderr)
        return None


def find_csv_in_zip(zip_bytes: bytes, hint: str) -> tuple[str, str] | None:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        candidates = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not candidates:
            return None
        preferred = [n for n in candidates if hint.lower() in n.lower()]
        chosen = preferred[0] if preferred else candidates[0]
        return chosen, zf.read(chosen).decode("latin-1")


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cow_mids (
            dispute_number INTEGER,
            side_a_state TEXT,
            side_b_state TEXT,
            start_year INTEGER,
            end_year INTEGER,
            hostility_level INTEGER,
            outcome INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_cow_mids_hostility ON cow_mids(hostility_level);

        CREATE TABLE IF NOT EXISTS cow_wars (
            war_number INTEGER,
            war_name TEXT,
            start_year INTEGER,
            end_year INTEGER,
            outcome INTEGER,
            duration_days INTEGER
        );

        CREATE TABLE IF NOT EXISTS cow_capabilities (
            state_name TEXT,
            year INTEGER,
            cinc REAL
        );
        CREATE INDEX IF NOT EXISTS idx_cow_capabilities_state_year
            ON cow_capabilities(state_name, year);
        """
    )
    conn.commit()


def _get(row: dict, *keys: str):
    """Case-insensitive, multi-alias field lookup — CoW's exact column names/
    casing have varied across dataset versions (e.g. `StYear` vs `styear` vs
    `StartYr1`)."""
    lower_row = {k.lower(): v for k, v in row.items()}
    for key in keys:
        value = lower_row.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def load_mids(conn: sqlite3.Connection, csv_text: str) -> int:
    """Loads CoW MIDA (dispute-level) rows: dispnum, styear, endyear, hostlev,
    outcome. MIDA has no participant/state columns (that's MIDB, dyadic) —
    side_a_state/side_b_state are left blank, which is fine since the
    base-rate step (Step 5) only uses year/hostility/outcome."""
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = []
    for row in reader:
        try:
            dispute_number = int(_get(row, "dispnum", "dispnum3"))
            start_year = int(_get(row, "styear", "styear"))
        except (TypeError, ValueError):
            continue
        rows.append(
            (
                dispute_number,
                (_get(row, "stateabb") or "").strip(),
                "",
                start_year,
                _int_or_none(_get(row, "endyear")),
                _int_or_none(_get(row, "hostlev")),
                _int_or_none(_get(row, "outcome")),
            )
        )
    conn.executemany(
        "INSERT INTO cow_mids (dispute_number, side_a_state, side_b_state, start_year, "
        "end_year, hostility_level, outcome) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def load_wars(conn: sqlite3.Connection, csv_text: str) -> int:
    """Accepts either Inter-State War v4.0 (`StartYear1`/`EndYear1`) or
    Intra-State War v5.1 (`StartYr1`/`EndYr1`) column layouts — both share
    WarNum/WarName/Outcome, and CoW has used both stem spellings across
    dataset versions."""
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = []
    for row in reader:
        try:
            war_number = int(_get(row, "warnum"))
            start_year = int(_get(row, "startyear1", "startyr1"))
        except (TypeError, ValueError):
            continue
        rows.append(
            (
                war_number,
                (_get(row, "warname") or "").strip(),
                start_year,
                _int_or_none(_get(row, "endyear1", "endyr1")),
                _int_or_none(_get(row, "outcome")),
                _int_or_none(_get(row, "wduratdays")),
            )
        )
    conn.executemany(
        "INSERT INTO cow_wars (war_number, war_name, start_year, end_year, outcome, duration_days) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def load_capabilities(conn: sqlite3.Connection, csv_text: str) -> int:
    """`stateabb` (e.g. "USA") is used as state_name — the NMC abridged file
    doesn't include a full-name column, and abbreviations are unambiguous
    for exact-match lookups anyway. Falls back to `statenme`/`statename` if
    present (e.g. the non-abridged/supplementary NMC file)."""
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = []
    for row in reader:
        state_name = (_get(row, "stateabb", "statenme", "statename") or "").strip()
        year = _get(row, "year")
        if not state_name or year is None:
            continue
        try:
            year = int(year)
        except (TypeError, ValueError):
            continue
        rows.append((state_name, year, _float_or_none(_get(row, "cinc"))))
    conn.executemany(
        "INSERT INTO cow_capabilities (state_name, year, cinc) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def _int_or_none(value) -> int | None:
    """CoW uses negative sentinel codes (-7/-8/-9) for missing/inapplicable
    data across all its datasets; every real code CoW uses is non-negative,
    so any negative value is treated as missing."""
    try:
        if value in (None, "", "."):
            return None
        parsed = int(float(value))
        return parsed if parsed >= 0 else None
    except (ValueError, TypeError):
        return None


def _float_or_none(value) -> float | None:
    try:
        if value in (None, "", "."):
            return None
        parsed = float(value)
        return parsed if parsed >= 0 else None
    except (ValueError, TypeError):
        return None


def main() -> int:
    settings = get_settings()
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    settings.cow_data_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(settings.sqlite_path)
    create_tables(conn)

    loaders = {"mids": load_mids, "wars": load_wars, "capabilities": load_capabilities}
    any_loaded = False

    for name, spec in DATASETS.items():
        manual_csv_path = settings.cow_data_dir / f"{name}.csv"
        if manual_csv_path.exists():
            print(f"Found manually-placed {manual_csv_path}, loading it directly.")
            csv_text = manual_csv_path.read_text(encoding="utf-8", errors="replace")
            n = loaders[name](conn, csv_text)
            print(f"  loaded {n} rows from {manual_csv_path.name} into cow_{name}")
            any_loaded = any_loaded or n > 0
            continue

        print(f"Fetching {name} from {spec['url']} ...")
        cache_path = settings.cow_data_dir / f"{name}.zip"
        if cache_path.exists():
            zip_bytes = cache_path.read_bytes()
            print(f"  using cached {cache_path}")
        else:
            zip_bytes = download_zip(spec["url"], settings.cow_data_dir)
            if zip_bytes:
                cache_path.write_bytes(zip_bytes)

        if not zip_bytes:
            print(f"  SKIPPED {name}: could not download and no cache present.")
            continue

        found = find_csv_in_zip(zip_bytes, spec["csv_hint"])
        if not found:
            print(f"  SKIPPED {name}: no CSV found in archive.")
            continue

        csv_name, csv_text = found
        # Save raw CSV alongside the zip for transparency / manual inspection.
        manual_csv_path.write_text(csv_text, encoding="utf-8")

        n = loaders[name](conn, csv_text)
        print(f"  loaded {n} rows from {csv_name} into cow_{name}")
        any_loaded = any_loaded or n > 0

    conn.close()

    if not any_loaded:
        print(
            "\nWARNING: no CoW data was loaded. Base-rate queries (Step 5) will fail until "
            "data/cow/ contains the datasets. You can also manually download CSVs from "
            "https://correlatesofwar.org/data-sets/ and place them at "
            f"{settings.cow_data_dir} as mids.csv / wars.csv / capabilities.csv, then re-run.",
            file=sys.stderr,
        )
        return 1

    print(f"\nDone. SQLite database at {settings.sqlite_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
