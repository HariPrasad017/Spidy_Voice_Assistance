"""
S.P.I.D.Y v6.1 — Context Resolver
A lightweight layer that analyses the current user message against conversation
history to produce an explicit context state before the main LLM call.

This does NOT hardcode rules for specific entities.  It uses a fast, cheap
LLM call to extract structured context, which is then injected into the main
prompt as a grounded summary.  The full raw history is still passed so the
main LLM call retains all details.
"""

import json
import logging
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import GROQ_MODEL, logger, groq_circuit_breaker

# Freshness keywords — trigger web-search rather than static LLM knowledge
FRESHNESS_TRIGGERS = {
    "current", "latest", "today", "now", "recently", "this week", "this month",
    "right now", "at the moment", "as of", "who is the", "what is the current",
    "current ceo", "current president", "current prime minister", "current chief minister",
    "current cm", "current pm", "current government", "current election",
    "current news", "latest news", "breaking news", "new release", "just released",
    "latest version", "current price", "stock price", "live", "real-time",
    "latest job", "current openings", "current vacancies",
    "gold price", "silver price", "gold rate", "silver rate", "market rate",
    "market price", "per gram", "share price", "stock rate", "revenue of",
    "current revenue", "winner", "who won", "today's price", "price of", "rate of"
}

REFERENCE_WORDS = {
    "he", "she", "it", "they", "them", "him", "his", "her", "its", "their",
    "that", "this", "there", "here", "the company", "the person",
    "the same", "the first one", "the second one", "tell me more",
    "what about", "more about", "what else", "why", "how",
    "yes", "no", "sure", "okay", "ok", "go ahead", "continue",
    "singapore", "india", "london"  # short geographic clarifications
}


def needs_freshness(user_text: str) -> bool:
    """Return True if the query likely requires current information."""
    lower = user_text.lower()
    return any(trigger in lower for trigger in FRESHNESS_TRIGGERS)


def is_reference_only(user_text: str) -> bool:
    """Return True if the message is short and likely a reference/continuation."""
    import re
    clean = user_text.strip().lower()
    words = re.findall(r'\b\w+\b', clean)
    if len(words) <= 6:
        if any(w in REFERENCE_WORDS for w in words):
            return True
        for phrase in REFERENCE_WORDS:
            if " " in phrase and phrase in clean:
                return True
    return False


def resolve_context(user_text: str, history: list, groq_client, conv_id: str = "") -> dict:
    """
    Produce an explicit context state for the current user message.

    Returns a dict:
    {
        "resolved_query": str,          # What the user is actually asking
        "active_topic": str | None,     # e.g. "Prime Minister of India"
        "active_entity": str | None,    # e.g. "Narendra Modi"
        "pending_clarification": bool,  # Did the last assistant turn ask a question?
        "requires_web_search": bool,    # Should we fetch current info?
        "context_summary": str,         # One-sentence context for the main prompt
        "is_continuation": bool         # Is this a follow-up to a previous turn?
    }
    """
    # Default — pass-through if no history or no client
    default = {
        "resolved_query": user_text,
        "active_topic": None,
        "active_entity": None,
        "pending_clarification": False,
        "requires_web_search": needs_freshness(user_text),
        "context_summary": "",
        "is_continuation": False
    }

    if conv_id:
        try:
            from agent.database import get_pending_clarification
            pending = get_pending_clarification(conv_id)
            if pending and pending.get("candidate"):
                cand = pending["candidate"]
                clean = user_text.lower().strip()
                affirmatives = {
                    'yes', 'yeah', 'yep', 'yup', 'sure', 'ok', 'okay',
                    'correct', "that's correct", "that is correct",
                    "that's right", "that is right", "exactly",
                    "yes that's it", "yes that's right", "confirm", "proceed"
                }
                if clean in affirmatives or any(clean.startswith(a) for a in affirmatives) or cand.lower() in clean:
                    return {
                        "resolved_query": cand,
                        "active_topic": cand,
                        "active_entity": cand,
                        "pending_clarification": False,
                        "requires_web_search": needs_freshness(cand),
                        "context_summary": f"User confirmed candidate: {cand}",
                        "is_continuation": True
                    }
        except Exception as e:
            logger.debug(f"[ContextResolver] Pending check non-fatal: {e}")

    if not groq_client or not history:
        return default

    # Circuit breaker check: do not call Groq if circuit is open
    is_blocked, _ = groq_circuit_breaker.check_circuit()
    if is_blocked:
        return default

    # Rule C: Context resolution should ONLY run when the current request actually requires a prior referent
    clean_low = user_text.strip().lower()
    words = set(re.findall(r'\b\w+\b', clean_low))
    pronouns = {"he", "she", "it", "they", "them", "him", "his", "her", "its", "their", "that", "this"}
    has_pronoun = bool(words & pronouns)
    has_ref_phrase = any(p in clean_low for p in ["tell me more", "what about", "more about", "what else", "the same", "the first one", "the second one", "why", "how"])
    
    if not is_reference_only(user_text) and not has_pronoun and not has_ref_phrase:
        # Standalone query: does NOT require prior referent resolution
        return {**default, "requires_web_search": needs_freshness(user_text)}

    # Build a compact history string (last 6 turns max)
    recent = history[-6:] if len(history) > 6 else history
    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content'][:300]}" for m in recent
    )

    resolver_prompt = f"""You are a context resolution assistant.
Given the conversation history and the new user message, extract the following
as a compact JSON object (no extra text, valid JSON only):

{{
  "resolved_query": "<The complete, self-contained question the user is really asking>",
  "active_topic": "<Current topic being discussed, or null>",
  "active_entity": "<Primary entity (person/company/place) in context, or null>",
  "pending_clarification": <true if the last assistant message asked a clarifying question>,
  "requires_web_search": <true if the question needs current/live information>,
  "context_summary": "<One sentence: what the conversation is about>",
  "is_continuation": <true if this is a follow-up to a previous topic>
}}

Rules:
- resolved_query must be a COMPLETE, standalone question — not just the raw user text.
- PRIORITY: Resolve confirmations ("yes", "correct", etc.) or references against the IMMEDIATELY preceding assistant turn or pending clarification candidate, NEVER against older displaced topics.
- If user says "India" after assistant asked "Did you mean India or Ireland?",
  resolved_query should be the FULL question with "India" substituted in.
- If user says "he" after discussing Narendra Modi, resolved_query should name Modi.
- If unclear, keep resolved_query as the original user text.
- requires_web_search = true for: current office holders, recent news, today's weather,
  latest releases, current prices, live events, current jobs.

CONVERSATION HISTORY:
{history_text}

NEW USER MESSAGE: {user_text}

JSON:"""

    try:
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": resolver_prompt}],
            max_tokens=180,
            temperature=0.1
        )
        raw = (resp.choices[0].message.content or "").strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start:end+1]
        elif raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        ctx = json.loads(raw)
        logger.info(f"[ContextResolver] {ctx}")
        return ctx
    except Exception as e:
        if "429" in str(e) or "rate" in str(e).lower():
            groq_circuit_breaker.record_429(e)
        logger.warning(f"[ContextResolver] Failed ({e}), using defaults")
        return default
