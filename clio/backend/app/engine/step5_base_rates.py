"""Step 5 — Base rates from real data.

Builds a reference class from the local Correlates of War tables, filtered
by the scenario's stakes_framing/escalation_position dimensions translated
into a hostility-level MID filter. Every number in the output table comes
directly from the CoW dataset — never from the LLM — and the exact filter
used is included as `query_definition` for transparency.

Limitation (documented in the query definition itself, not hidden): CINC-
ratio filtering by power_asymmetry requires named real-world states on both
sides of the dispute. CLIO's scenarios describe generic actors ("a mid-size
power"), so this reference class is built from the hostility-level filter
only; a future version could resolve the scenario's actors to CoW state
codes (via the verified historical analogues' real actor names) to add a
CINC-ratio filter on top of this.
"""
from app.models.report import BaseRateRow, BaseRateTable
from app.models.scenario import Scenario
from app.sources.cow import CoWDataClient, CoWDataUnavailableError, MidRecord

# CoW MIDB 5.0 hostility levels: 1=No militarized action, 2=Threat to use force,
# 3=Display of force, 4=Use of force, 5=War.
WAR_HOSTILITY_LEVEL = 5
SUB_WAR_MIN_HOSTILITY = 3

# CoW MIDB 5.0 dyadic `sidea`-relative outcome codes (simplified bucketing for this table):
# 1 = Victory for side A, 5 = Stalemate, 6 = Compromise; everything else (yield, released,
# unclear, ongoing, etc.) is bucketed as "other/unresolved". We treat "side A" as a proxy for
# the initiator, which is an approximation — CoW does not encode initiator/target roles
# directly in this abridged ingest.
OUTCOME_INITIATOR_ACHIEVED = {1}
OUTCOME_STALEMATE = {5, 6}


def _bucket_outcome(mid: MidRecord) -> str:
    if mid.outcome in OUTCOME_INITIATOR_ACHIEVED:
        return "initiator achieved objectives"
    if mid.outcome in OUTCOME_STALEMATE:
        return "stalemate"
    return "failed / other outcome"


def _stakes_wants_war_level(scenario: Scenario) -> bool:
    text = f"{scenario.dimensions.stakes_framing} {scenario.dimensions.escalation_position}".lower()
    return any(kw in text for kw in ("war", "existential", "total"))


def build_base_rate_table(scenario: Scenario, cow_client: CoWDataClient | None = None) -> BaseRateTable:
    cow_client = cow_client or CoWDataClient()

    if not cow_client.is_available():
        return BaseRateTable(
            query_definition=(
                "CoW data not available locally (run backend/scripts/setup_data.py). "
                "No base-rate table could be computed."
            ),
            n_cases=0,
            rows=[],
            source="Correlates of War",
        )

    war_only = _stakes_wants_war_level(scenario)
    min_hostility = WAR_HOSTILITY_LEVEL if war_only else SUB_WAR_MIN_HOSTILITY
    max_hostility = WAR_HOSTILITY_LEVEL

    try:
        mids = cow_client.query_mids(min_hostility=min_hostility, max_hostility=max_hostility)
    except CoWDataUnavailableError:
        return BaseRateTable(
            query_definition="CoW data became unavailable while querying.",
            n_cases=0,
            rows=[],
            source="Correlates of War",
        )

    query_definition = (
        f"Correlates of War MIDs 5.0, dyadic participant rows, filtered to hostility_level "
        f"between {min_hostility} and {max_hostility} "
        f"({'war-level disputes only' if war_only else 'sub-war and war-level disputes'}), "
        "derived from the scenario's stakes_framing/escalation_position dimensions. "
        "Outcome buckets approximate 'initiator achieved objectives' as CoW outcome code 1 "
        "(victory for side A), 'stalemate' as codes 5-6 (stalemate/compromise), and everything "
        "else as 'failed / other outcome' — CoW does not encode initiator/target roles "
        "directly, so 'side A' is used as a proxy. CINC-ratio filtering by power asymmetry was "
        "not applied because this scenario's actors are generic, not named real-world states."
    )

    if not mids:
        return BaseRateTable(query_definition=query_definition, n_cases=0, rows=[], source="Correlates of War")

    counts: dict[str, int] = {}
    for mid in mids:
        bucket = _bucket_outcome(mid)
        counts[bucket] = counts.get(bucket, 0) + 1

    n = len(mids)
    rows = [
        BaseRateRow(outcome=outcome, count=count, pct=round(100 * count / n, 1))
        for outcome, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]

    durations = [
        (mid.end_year - mid.start_year) * 365
        for mid in mids
        if mid.end_year is not None and mid.end_year >= mid.start_year
    ]
    mean_duration_days = round(sum(durations) / len(durations), 1) if durations else None

    war_count = sum(1 for mid in mids if mid.hostility_level == WAR_HOSTILITY_LEVEL)
    escalation_to_war_rate = round(war_count / n, 3) if n else None

    return BaseRateTable(
        query_definition=query_definition,
        n_cases=n,
        rows=rows,
        mean_duration_days=mean_duration_days,
        escalation_to_war_rate=escalation_to_war_rate,
        source="Correlates of War",
    )
