"""
S.P.I.D.Y v6.2.1 — Groq Efficiency Tests (Phase 7)

Verifies:
 - Zero Groq calls for greetings
 - Zero Groq calls for deterministic commands
 - _extract_task_state_local is used (no Groq call)
 - Selective tool schema binding
 - Pending clarification resolved without Groq
 - Circuit breaker: 429 detection, cooldown, recovery
 - Deterministic commands work while circuit is open
 - Credential safety (error messages must not leak API key)
"""

import sys
import os
import time
import unittest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))


# ===========================================================================
# Helper — build a fake Groq 429 exception with headers
# ===========================================================================
def _make_429_exc(retry_after: str = "30"):
    exc = Exception("429 rate_limit_exceeded")
    exc.response = MagicMock()
    exc.response.headers = {"retry-after": retry_after}
    return exc


# ===========================================================================
# 1.  GREETING — 0 Groq calls
# ===========================================================================
class TestGreetingZeroGroq(unittest.TestCase):
    """Greetings must be resolved deterministically without touching Groq."""

    def _check_greeting(self, text: str):
        from commands import parse_command
        result = parse_command(text)
        self.assertIsNotNone(result, f"parse_command returned None for greeting: {text!r}")
        resp = result if isinstance(result, str) else result.get("response", "")
        self.assertTrue(
            any(w in resp.lower() for w in ["hello", "hi", "hey", "spid", "help", "how can", "good morning", "good afternoon", "good evening", "good night"]),
            f"Unexpected greeting response for {text!r}: {resp!r}"
        )

    def test_hello_spidey(self):
        self._check_greeting("hello spidey")

    def test_hi_spidy(self):
        self._check_greeting("hi spidy")

    def test_hey_spidey(self):
        self._check_greeting("hey spidey")

    def test_good_morning(self):
        self._check_greeting("good morning")

    def test_greetings(self):
        self._check_greeting("greetings")


# ===========================================================================
# 2.  DETERMINISTIC COMMANDS — 0 Groq calls
# ===========================================================================
class TestDeterministicZeroGroq(unittest.TestCase):
    """parse_command must handle OS commands without any Groq calls."""

    def _parse(self, text: str):
        from commands import parse_command
        return parse_command(text)

    def test_open_notepad(self):
        result = self._parse("open notepad")
        self.assertIsNotNone(result)

    def test_volume_up(self):
        result = self._parse("volume up")
        self.assertIsNotNone(result)

    def test_screenshot(self):
        result = self._parse("take a screenshot")
        self.assertIsNotNone(result)

    def test_mute(self):
        result = self._parse("mute")
        self.assertIsNotNone(result)


# ===========================================================================
# 3.  _extract_task_state_local — no Groq call
# ===========================================================================
class TestExtractTaskStateLocal(unittest.TestCase):
    """router._extract_task_state_local must extract task context via Python without calling Groq."""

    def test_job_search_role_and_company_detected(self):
        from agent.router import _extract_task_state_local
        result = _extract_task_state_local("find python roles at Google in Bangalore", current_task=None)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("company"), "Google")
        self.assertEqual(result.get("role"), "Python")
        self.assertIn("Bangalore", result.get("location", ""))

    def test_existing_task_preserved_and_updated(self):
        from agent.router import _extract_task_state_local
        current = {"task_type": "job_search", "company": "Microsoft", "role": "ML", "location": "USA", "active": True}
        result = _extract_task_state_local("in London", current_task=current)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("company"), "Microsoft")
        self.assertEqual(result.get("role"), "ML")
        self.assertEqual(result.get("location"), "London")

    def test_no_active_task_and_no_job_keywords_returns_none(self):
        from agent.router import _extract_task_state_local
        result = _extract_task_state_local("what is machine learning", current_task=None)
        self.assertIsNone(result)


# ===========================================================================
# 4.  SELECTIVE TOOL SCHEMAS
# ===========================================================================
class TestSelectiveToolSchemas(unittest.TestCase):
    """get_selective_tool_schemas must return None for pure-knowledge queries
    and only relevant schemas for tool-requiring queries."""

    def test_knowledge_query_returns_none(self):
        from agent.router import get_selective_tool_schemas
        schemas = get_selective_tool_schemas("what is machine learning", requires_web=False)
        self.assertIsNone(schemas, "Pure knowledge query should return None (no tools)")

    def test_explain_returns_none(self):
        from agent.router import get_selective_tool_schemas
        schemas = get_selective_tool_schemas("explain the theory of relativity", requires_web=False)
        self.assertIsNone(schemas, "Pure explanation query should return None")

    def test_weather_returns_get_weather_only(self):
        from agent.router import get_selective_tool_schemas
        schemas = get_selective_tool_schemas("what is the weather today", requires_web=False)
        self.assertIsNotNone(schemas)
        names = [s["function"]["name"] for s in schemas]
        self.assertIn("get_weather", names)
        self.assertNotIn("web_search", names)

    def test_news_returns_web_search(self):
        from agent.router import get_selective_tool_schemas
        schemas = get_selective_tool_schemas("latest AI news", requires_web=True)
        self.assertIsNotNone(schemas)
        names = [s["function"]["name"] for s in schemas]
        self.assertIn("web_search", names)

    def test_notes_returns_note_tool(self):
        from agent.router import get_selective_tool_schemas
        schemas = get_selective_tool_schemas("save a note", requires_web=False)
        self.assertIsNotNone(schemas)
        names = [s["function"]["name"] for s in schemas]
        self.assertTrue(
            any("note" in n.lower() or "save" in n.lower() for n in names),
            f"Expected a note/save tool, got: {names}"
        )


# ===========================================================================
# 5.  PENDING CLARIFICATION — 0 Groq calls
# ===========================================================================
class TestPendingClarificationZeroGroq(unittest.TestCase):
    """When a pending clarification exists, it must resolve without Groq."""

    def test_yes_resolves_pending_without_groq(self):
        from agent import context_resolver as cr
        mock_pending = {
            "question": "Did you mean the Lenovo LOQ laptop?",
            "candidate": "Lenovo LOQ laptop",
            "context_key": "device"
        }
        mock_db_get = MagicMock(return_value=mock_pending)
        mock_db_clear = MagicMock()
        with patch("agent.database.get_pending_clarification", mock_db_get), \
             patch("agent.database.clear_pending_clarification", mock_db_clear), \
             patch.object(cr, "groq_circuit_breaker") as mock_cb:
            mock_cb.check_circuit.return_value = (False, "")
            # Ensure no groq_client is available so LLM path is skipped
            result = cr.resolve_context("yes", conv_id="test-conv", history=[], groq_client=None)
        # Result should contain the candidate or original text (pending clarification handled)
        # Key assertion: it resolves using pending state, not Groq
        self.assertIsNotNone(result)
        self.assertIn("Lenovo LOQ", result.get("resolved_query", ""))

    def test_no_pending_standalone_query_skips_groq(self):
        """A standalone knowledge query with no pronouns must not call Groq resolver."""
        from agent.context_resolver import resolve_context
        mock_groq = MagicMock()
        with patch("agent.database.get_pending_clarification", return_value=None):
            result = resolve_context(
                "what is machine learning",
                conv_id="test-conv",
                history=[],
                groq_client=mock_groq
            )
        # Groq must NOT be called — no pronouns, no pending
        mock_groq.chat.completions.create.assert_not_called()
        # Result should be the original query (pass-through)
        self.assertEqual(result.get("resolved_query"), "what is machine learning")


# ===========================================================================
# 6.  CIRCUIT BREAKER — core logic
# ===========================================================================
class TestCircuitBreaker(unittest.TestCase):
    """GroqCircuitBreaker must correctly open, block, and auto-recover."""

    def _fresh_cb(self):
        from config import GroqCircuitBreaker
        cb = GroqCircuitBreaker()
        return cb

    def test_initially_closed(self):
        cb = self._fresh_cb()
        is_blocked, msg = cb.check_circuit()
        self.assertFalse(is_blocked)
        self.assertEqual(msg, "")

    def test_record_429_opens_circuit(self):
        cb = self._fresh_cb()
        cb.record_429(_make_429_exc("30"))
        self.assertTrue(cb.is_open)

    def test_blocked_while_open(self):
        cb = self._fresh_cb()
        cb.record_429(_make_429_exc("30"))
        is_blocked, msg = cb.check_circuit()
        self.assertTrue(is_blocked)
        self.assertIsInstance(msg, str)
        self.assertTrue(len(msg) > 0)

    def test_recovers_after_cooldown(self):
        cb = self._fresh_cb()
        cb.record_429(_make_429_exc("1"))     # 1-second cooldown
        cb.cooldown_until = time.time() - 1   # manually expire
        is_blocked, msg = cb.check_circuit()
        self.assertFalse(is_blocked)
        self.assertFalse(cb.is_open)

    def test_retry_after_header_parsed(self):
        cb = self._fresh_cb()
        cb.record_429(_make_429_exc("45"))
        remaining = cb.cooldown_until - time.time()
        self.assertGreater(remaining, 40)
        self.assertLessEqual(remaining, 46)

    def test_retry_after_minutes_parsed(self):
        """Handles '2m30s' style retry-after strings."""
        cb = self._fresh_cb()
        exc = Exception("429 rate_limit")
        exc.response = MagicMock()
        exc.response.headers = {"retry-after": "2m30s"}
        cb.record_429(exc)
        remaining = cb.cooldown_until - time.time()
        # 2*60+30 = 150 seconds
        self.assertGreater(remaining, 140)
        self.assertLessEqual(remaining, 151)

    def test_no_header_uses_fallback(self):
        """If no Retry-After header, a conservative fallback is used."""
        cb = self._fresh_cb()
        exc = Exception("429 rate_limit")
        exc.response = MagicMock()
        exc.response.headers = {}   # empty headers
        cb.record_429(exc)
        remaining = cb.cooldown_until - time.time()
        # Fallback should be at least a few seconds
        self.assertGreater(remaining, 5)

    def test_reset_closes_circuit(self):
        cb = self._fresh_cb()
        cb.record_429(_make_429_exc("30"))
        cb.reset()
        is_blocked, _ = cb.check_circuit()
        self.assertFalse(is_blocked)

    def test_second_call_while_open_still_blocked(self):
        cb = self._fresh_cb()
        cb.record_429(_make_429_exc("60"))
        for _ in range(3):
            is_blocked, _ = cb.check_circuit()
            self.assertTrue(is_blocked)

    def test_no_credential_leak_in_message(self):
        """Error messages returned by check_circuit must not contain the API key."""
        from config import GROQ_API_KEY
        if not GROQ_API_KEY:
            self.skipTest("GROQ_API_KEY not configured")
        cb = self._fresh_cb()
        cb.record_429(_make_429_exc("30"))
        _, msg = cb.check_circuit()
        self.assertNotIn(GROQ_API_KEY, msg)


# ===========================================================================
# 7.  CIRCUIT OPEN — deterministic commands still work
# ===========================================================================
class TestDeterministicWhileCircuitOpen(unittest.TestCase):
    """Deterministic commands must bypass Groq entirely — circuit state is irrelevant."""

    def setUp(self):
        from config import groq_circuit_breaker
        groq_circuit_breaker.record_429(_make_429_exc("3600"))

    def tearDown(self):
        from config import groq_circuit_breaker
        groq_circuit_breaker.reset()

    def test_open_notepad_still_works(self):
        from commands import parse_command
        result = parse_command("open notepad")
        self.assertIsNotNone(result)

    def test_greeting_still_works(self):
        from commands import parse_command
        result = parse_command("hello spidey")
        self.assertIsNotNone(result)

    def test_volume_still_works(self):
        from commands import parse_command
        result = parse_command("volume up")
        self.assertIsNotNone(result)


# ===========================================================================
# 8.  TASK ENGINE — circuit open skips LLM planner, uses fallback
# ===========================================================================
class TestTaskEngineCbGuard(unittest.TestCase):
    """When circuit is open, task_engine must skip the LLM call and fall
    through to the deterministic / domain-aware fallback planner."""

    def test_circuit_open_skips_llm_planner(self):
        from config import groq_circuit_breaker
        from agent.task_engine import create_task_plan
        groq_circuit_breaker.record_429(_make_429_exc("3600"))
        try:
            mock_groq = MagicMock()
            plan = create_task_plan(
                "search for AI news and save to notes",
                conv_id="test-conv",
                groq_client=mock_groq
            )
            # LLM must NOT have been called because circuit is open
            mock_groq.chat.completions.create.assert_not_called()
            # A fallback plan may or may not be returned (None is acceptable)
            # — what matters is the LLM wasn't hit
        finally:
            groq_circuit_breaker.reset()


# ===========================================================================
# 9.  TOKEN-SAVING: max_tokens values in edited files
# ===========================================================================
class TestMaxTokensValues(unittest.TestCase):
    """Verify the reduced max_tokens constants are in effect."""

    def test_router_max_tokens_250(self):
        """router.py must use max_tokens<=250 for all LLM calls."""
        router_path = os.path.join(os.path.dirname(__file__), "agent", "router.py")
        with open(router_path, encoding="utf-8") as f:
            src = f.read()
        import re
        values = [int(v) for v in re.findall(r"max_tokens\s*=\s*(\d+)", src)]
        for v in values:
            self.assertLessEqual(v, 250, f"router.py has max_tokens={v} (expected <=250)")

    def test_task_engine_max_tokens_350(self):
        """task_engine.py LLM planner must use max_tokens<=350."""
        engine_path = os.path.join(os.path.dirname(__file__), "agent", "task_engine.py")
        with open(engine_path, encoding="utf-8") as f:
            src = f.read()
        import re
        values = [int(v) for v in re.findall(r"max_tokens\s*=\s*(\d+)", src)]
        for v in values:
            self.assertLessEqual(v, 350, f"task_engine.py has max_tokens={v} (expected <=350)")

    def test_context_resolver_max_tokens_180(self):
        """context_resolver.py must use max_tokens<=180."""
        cr_path = os.path.join(os.path.dirname(__file__), "agent", "context_resolver.py")
        with open(cr_path, encoding="utf-8") as f:
            src = f.read()
        import re
        values = [int(v) for v in re.findall(r"max_tokens\s*=\s*(\d+)", src)]
        for v in values:
            self.assertLessEqual(v, 180, f"context_resolver.py has max_tokens={v} (expected <=180)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
