#!/usr/bin/env python3
"""Evict stale/overflow entries from the structured-case cache.

Run periodically (e.g. via cron) to keep the transient case cache bounded:

    python backend/scripts/evict_cache.py --max-age-days 90 --max-entries 1000

Cases are meant to be cached transiently (see docs/ARCHITECTURE.md) — this
does not delete anything a user is actively relying on; a case dropped here
simply gets re-fetched and re-verified against current sources the next
time it's nominated.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache.db import CaseCache  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-age-days", type=int, default=90, help="Evict cases not refreshed in this many days")
    parser.add_argument("--max-entries", type=int, default=1000, help="Cap total cached cases, evicting oldest first")
    args = parser.parse_args()

    cache = CaseCache()
    stale_evicted = cache.evict_stale(max_age_days=args.max_age_days)
    lru_evicted = cache.evict_lru(max_entries=args.max_entries)

    print(f"Evicted {stale_evicted} stale case(s) (older than {args.max_age_days} days).")
    print(f"Evicted {lru_evicted} case(s) over the {args.max_entries}-entry cap.")
    print(f"Remaining cached cases: {len(cache.list_all())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
