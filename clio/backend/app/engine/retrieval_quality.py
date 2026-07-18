"""Retrieval-quality checks: keyword heuristics for verifying that Step 2
nomination actually surfaces the analogue class a scenario calls for, used
by both the retrieval-quality test suite and (optionally) a live QA run.

This is a heuristic, not a semantic judge — it exists to catch gross
retrieval failures (e.g. nominating nothing appeasement-adjacent for a
textbook appeasement scenario), not to grade analogy quality.
"""
from app.engine.step2_nominate import NominatedCandidate

APPEASEMENT_KEYWORDS = (
    "munich",
    "appeasement",
    "sudetenland",
    "anschluss",
    "czechoslovakia",
    "chamberlain",
    "hitler",
    "rhineland",
)


def contains_keyword_class(candidates: list[NominatedCandidate], keywords: tuple[str, ...]) -> bool:
    """True if any candidate's name/rationale/title mentions one of the given keywords."""
    haystack_by_candidate = [
        f"{c.name} {c.structural_rationale} {c.wikipedia_title}".lower() for c in candidates
    ]
    return any(any(kw in haystack for kw in keywords) for haystack in haystack_by_candidate)
