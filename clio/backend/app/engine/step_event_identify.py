"""Step E1 — Event identification (historical-event-analysis mode).

Given free text describing something that actually happened (e.g. "the US
backing the Mujahideen against the USSR in Afghanistan"), resolve it to ONE
specific, real, verifiable historical event/decision with an exact
Wikipedia title — the same grounding contract Step 2's nominations use, so
it can be fed straight into the existing verify_and_enrich firewall.

This is deliberately narrower than Step 2: it must resolve to exactly one
real event, not propose several, and refuses rather than guessing if the
text is too vague or doesn't correspond to a real, checkable event.
"""
from pydantic import BaseModel

from app.engine.llm import structured_call

SYSTEM_PROMPT = """You are a historian identifying which specific real historical event or \
decision a user is asking about, so it can be looked up and verified against Wikipedia/Wikidata.

Given free text describing a past event or decision, resolve it to ONE specific historical \
event/decision:
- Give a concise canonical name, an approximate date range, and the EXACT title of the English \
  Wikipedia article that covers it (get this precise, including capitalization) — prefer the \
  article that most specifically covers the DECISION or POLICY described (e.g. a covert-support \
  program), falling back to the broader conflict/event article if no more specific one exists.
- Only resolve to events/decisions you are confident are real and have a real English Wikipedia \
  article. Do not invent one.
- If the text is too vague to identify a single specific event, describes something that isn't \
  a real historical event, or plausibly refers to several different events, set found=false and \
  explain why in not_found_reason — do not guess."""


class IdentifiedEvent(BaseModel):
    found: bool
    name: str = ""
    approximate_dates: str = ""
    wikipedia_title: str = ""
    not_found_reason: str = ""


async def identify_event(raw_text: str) -> IdentifiedEvent:
    return await structured_call(
        system=SYSTEM_PROMPT,
        user=f"Text describing a past event or decision:\n\n{raw_text}",
        response_model=IdentifiedEvent,
    )
