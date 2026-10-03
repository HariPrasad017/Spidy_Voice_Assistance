"""
S.P.I.D.Y v6.2.1 — Hardening Regression Tests
Tests targeted at the new reliability/hardening features introduced in v6.2.1.
Run with: python -m unittest test_spidy_621.py
"""
import unittest
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ─── Test Group A: False Task-Success Prevention ─────────────────────────────

class TestFalseSuccessPrevention(unittest.TestCase):
    """Task only reaches COMPLETED when every step truly succeeds."""

    def test_classify_unsupported_result(self):
        """classify_tool_result must return UNSUPPORTED for unsupported-capability messages."""
        from agent.task_engine import classify_tool_result
        status, _ = classify_tool_result(
            "unsupported_desktop_action",
            "I can open Notepad, but arbitrary desktop typing and file saving are not currently supported."
        )
        self.assertEqual(status, "UNSUPPORTED")

    def test_classify_no_result_for_web_search(self):
        """classify_tool_result must return NO_RESULT for web search with no content."""
        from agent.task_engine import classify_tool_result
        status, _ = classify_tool_result(
            "web_search",
            "No Wikipedia results found for that query."
        )
        self.assertEqual(status, "NO_RESULT")

    def test_classify_timeout_result(self):
        """classify_tool_result must return TIMEOUT for timed-out results."""
        from agent.task_engine import classify_tool_result
        status, _ = classify_tool_result(
            "web_search",
            "Request timed out after 10 seconds."
        )
        self.assertEqual(status, "TIMEOUT")

    def test_classify_failed_security_rejection(self):
        """classify_tool_result must return FAILED for security rejections."""
        from agent.task_engine import classify_tool_result
        status, _ = classify_tool_result(
            "open_application",
            "For security reasons, 'trojan_virus.exe' is not in the allowed list."
        )
        self.assertEqual(status, "FAILED")

    def test_classify_success_for_positive_result(self):
        """classify_tool_result must return SUCCESS for clean tool output."""
        from agent.task_engine import classify_tool_result
        status, _ = classify_tool_result(
            "open_application",
            "Notepad opened successfully."
        )
        self.assertEqual(status, "SUCCESS")


# ─── Test Group B: Wrong-Domain Tool Validation ───────────────────────────────

class TestDomainValidation(unittest.TestCase):
    """validate_plan_domains blocks cross-domain tool assignment."""

    def test_desktop_typing_to_web_search_blocked(self):
        """A step requesting notepad + write must NOT be allowed to use web_search."""
        from agent.task_engine import validate_plan_domains
        task = {
            "original_request": "open notepad and write hello world",
            "steps": [
                {
                    "description": "Open notepad and write hello world",
                    "tool": "web_search",
                    "arguments": {"query": "open notepad and write hello world"}
                }
            ]
        }
        valid, code, msg = validate_plan_domains(task)
        self.assertFalse(valid)
        self.assertEqual(code, "WRONG_DOMAIN")

    def test_notes_save_passes_validation(self):
        """'Save to my notes' must NOT trigger wrong-domain block (uses save_note, not web_search)."""
        from agent.task_engine import validate_plan_domains
        task = {
            "original_request": "save that to my notes",
            "steps": [
                {
                    "description": "Save to notes",
                    "tool": "save_note",
                    "arguments": {"text": "some text"}
                }
            ]
        }
        valid, code, msg = validate_plan_domains(task)
        self.assertTrue(valid)
        self.assertIsNone(code)

    def test_web_search_for_info_query_passes(self):
        """web_search for a genuine information query must pass domain validation."""
        from agent.task_engine import validate_plan_domains
        task = {
            "original_request": "who is the current prime minister of india",
            "steps": [
                {
                    "description": "Search for current PM of India",
                    "tool": "web_search",
                    "arguments": {"query": "current prime minister of india"}
                }
            ]
        }
        valid, code, msg = validate_plan_domains(task)
        self.assertTrue(valid)


# ─── Test Group C: Unsupported Desktop/File Handling ─────────────────────────

class TestUnsupportedDesktopAction(unittest.TestCase):
    """Requests to type or save files report UNSUPPORTED, not a fabricated success."""

    def test_unsupported_desktop_action_tool_registered(self):
        """unsupported_desktop_action must exist in AVAILABLE_TOOLS."""
        from agent.tools import AVAILABLE_TOOLS
        self.assertIn("unsupported_desktop_action", AVAILABLE_TOOLS)

    def test_unsupported_desktop_action_returns_honest_message(self):
        """unsupported_desktop_action must return an honest, non-empty message."""
        from agent.tools import AVAILABLE_TOOLS
        func = AVAILABLE_TOOLS["unsupported_desktop_action"]["func"]
        result = func({"app_name": "notepad"})
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
        # Must NOT claim success
        self.assertNotIn("success", result.lower())
        # Must state the limitation
        lower = result.lower()
        self.assertTrue(
            "not currently supported" in lower or "not supported" in lower,
            f"Expected unsupported message, got: {result}"
        )

    def test_pattern_d_detected_for_open_notepad_write(self):
        """Multi-step request 'open notepad and write ...' must produce Pattern D plan."""
        from agent.task_engine import create_task_plan
        task = create_task_plan("open notepad and write hello and save as test.txt", "conv_D_test")
        step_tools = [s["tool"] for s in task["steps"]]
        self.assertIn("unsupported_desktop_action", step_tools)
        # Should NOT contain web_search for this input
        self.assertNotIn("web_search", step_tools)


# ─── Test Group D: Lenovo LOQ vs Workstation Lock Safety ─────────────────────

class TestLenovoLOQSafety(unittest.TestCase):
    """'Lenovo LOQ' must never trigger workstation lock."""

    def test_lenovo_loq_laptop_no_lock(self):
        """'Lenovo LOQ laptop' must not return a lock/security action."""
        from commands import parse_command
        result = parse_command("lenovo loq laptop")
        # parse_command returns None (pass-through to AI) — must NOT be a lock string
        if result is not None:
            lower = result.lower()
            self.assertNotIn("workstation locked", lower)
            self.assertNotIn("screen is now locked", lower)

    def test_lenovo_lock_returns_clarification(self):
        """'Lenovo lock laptop' must return a clarification, not execute lock."""
        from commands import parse_command
        result = parse_command("lenovo lock laptop")
        self.assertIsNotNone(result, "Should return clarification, not None")
        lower = result.lower()
        # Must NOT be a workstation-lock confirmation
        self.assertNotIn("workstation locked", lower)
        # Should mention lenovo or loq
        self.assertTrue(
            "lenovo" in lower or "loq" in lower or "laptop" in lower,
            f"Expected clarification mentioning Lenovo/LOQ, got: {result}"
        )

    def test_explicit_lock_computer_still_works(self):
        """Explicit 'lock my computer' must still be recognized as a lock command."""
        from commands import parse_command
        result = parse_command("lock my computer")
        # Should produce a lock result (not None, not a clarification)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)


# ─── Test Group E+F: Entity/Voice Recovery ───────────────────────────────────

class TestEntityRecovery(unittest.TestCase):
    """Speech-recognition misrecognitions must be corrected."""

    def test_l_space_o_space_q_normalizes_to_loq(self):
        """'l o q' spaced out must normalize to 'loq'."""
        from commands import normalize_voice_text
        result = normalize_voice_text("tell me about the l o q gaming laptop")
        self.assertIn("loq", result.lower())

    def test_l_dot_o_dot_q_normalizes_to_loq(self):
        """'l.o.q' must normalize to 'loq'."""
        from commands import normalize_voice_text
        result = normalize_voice_text("specs of l.o.q laptop")
        self.assertIn("loq", result.lower())

    def test_lenova_normalizes_to_lenovo(self):
        """'lenova' (common misrecognition) must normalize to 'lenovo'."""
        from commands import normalize_voice_text
        result = normalize_voice_text("tell me about lenova products")
        self.assertIn("lenovo", result.lower())


# ─── Test Group G+H+I: Provider Error Sanitization ───────────────────────────

class TestProviderErrorSanitization(unittest.TestCase):
    """sanitize_provider_error must return safe messages, never raw exception data."""

    def test_429_rate_limit_sanitized(self):
        """HTTP 429 must return a rate-limit user message."""
        from config import sanitize_provider_error
        result = sanitize_provider_error(Exception("HTTP 429 rate_limit_exceeded"))
        self.assertIsInstance(result, str)
        lower = result.lower()
        self.assertTrue(
            "rate" in lower or "limit" in lower or "try again" in lower,
            f"Expected rate-limit message, got: {result}"
        )
        # Must not expose raw exception content
        self.assertNotIn("429", result)
        self.assertNotIn("rate_limit_exceeded", result)

    def test_400_bad_request_sanitized(self):
        """HTTP 400 must return a safe rephrase-and-try message."""
        from config import sanitize_provider_error
        result = sanitize_provider_error(Exception("400 bad request invalid_request_error"))
        self.assertIsInstance(result, str)
        # Must not expose raw 400 code
        self.assertNotIn("400", result)
        # Must not expose internal error labels
        self.assertNotIn("invalid_request_error", result)

    def test_timeout_sanitized(self):
        """Timeout exception must return a clean timeout message."""
        from config import sanitize_provider_error
        result = sanitize_provider_error(Exception("Request timed out"))
        self.assertIsInstance(result, str)
        lower = result.lower()
        self.assertTrue(
            "timeout" in lower or "timed out" in lower or "try again" in lower,
            f"Expected timeout message, got: {result}"
        )

    def test_500_server_error_sanitized(self):
        """HTTP 500 must return a clean server-error message."""
        from config import sanitize_provider_error
        result = sanitize_provider_error(Exception("500 internal server error"))
        self.assertIsInstance(result, str)
        self.assertNotIn("500", result)
        self.assertNotIn("internal server error", result.lower())

    def test_sanitized_message_never_empty(self):
        """sanitize_provider_error must always return a non-empty string."""
        from config import sanitize_provider_error
        result = sanitize_provider_error(Exception("Some completely unknown error"))
        self.assertIsInstance(result, str)
        self.assertGreater(len(result.strip()), 0)


# ─── Test Group J: Freshness Routing for Finance/Commodities ─────────────────

class TestFreshnessRouting(unittest.TestCase):
    """Finance/commodity queries must route to 'finance' classifier, not 'stable'."""

    def _classify(self, query):
        from agent.tools import _classify_query
        return _classify_query(query)

    def test_gold_price_classifies_as_finance(self):
        self.assertEqual(self._classify("what is the gold price today"), "finance")

    def test_silver_rate_classifies_as_finance(self):
        self.assertEqual(self._classify("current silver rate in india"), "finance")

    def test_gold_per_gram_classifies_as_finance(self):
        self.assertEqual(self._classify("gold price per gram in india"), "finance")

    def test_stock_price_classifies_as_finance(self):
        self.assertEqual(self._classify("current stock price of reliance"), "finance")

    def test_freshness_trigger_gold_price(self):
        """needs_freshness must return True for 'gold price' queries."""
        from agent.context_resolver import needs_freshness
        self.assertTrue(needs_freshness("what is the current gold price in india"))

    def test_freshness_trigger_silver_rate(self):
        """needs_freshness must return True for 'silver rate' queries."""
        from agent.context_resolver import needs_freshness
        self.assertTrue(needs_freshness("silver rate per gram today"))


# ─── Test Group K: Source Integrity on Empty Results ─────────────────────────

class TestSourceIntegrity(unittest.TestCase):
    """Web search results on failure must return sources: [] not fabricated URLs."""

    def test_classify_no_result_for_live_search_failed(self):
        """'live search failed' result string must classify as NO_RESULT."""
        from agent.task_engine import classify_tool_result
        status, _ = classify_tool_result(
            "web_search",
            "Live search failed — no current data available."
        )
        self.assertEqual(status, "NO_RESULT")

    def test_classify_no_result_for_finance_retrieval_failure(self):
        """Finance retrieval failure message must classify as NO_RESULT."""
        from agent.task_engine import classify_tool_result
        status, _ = classify_tool_result(
            "web_search",
            "Verified real-time financial sources are currently unreachable. Please try again later."
        )
        self.assertEqual(status, "NO_RESULT")


# ─── Test Group L: Multi-Domain Task Planning ─────────────────────────────────

class TestMultiDomainTaskPlanning(unittest.TestCase):
    """Multi-step plans must use the correct tool per domain."""

    def test_open_app_and_weather_uses_pattern_b(self):
        """'Open notepad and tell me the weather' must produce open_application + get_weather."""
        from agent.task_engine import create_task_plan
        task = create_task_plan("open notepad and tell me the weather", "conv_B_test")
        step_tools = [s["tool"] for s in task["steps"]]
        self.assertIn("open_application", step_tools)
        self.assertIn("get_weather", step_tools)
        # Must NOT route weather lookup to web_search
        self.assertNotIn("web_search", step_tools)

    def test_tool_domains_dict_exists(self):
        """TOOL_DOMAINS must be importable and contain key tools."""
        from agent.task_engine import TOOL_DOMAINS
        self.assertIn("web_search", TOOL_DOMAINS)
        self.assertIn("open_application", TOOL_DOMAINS)
        self.assertIn("get_weather", TOOL_DOMAINS)
        self.assertIn("unsupported_desktop_action", TOOL_DOMAINS)


# ─── Test Group M: WAITING_CONFIRMATION State ─────────────────────────────────

class TestWaitingConfirmation(unittest.TestCase):
    """Steps with requires_confirmation=True must produce WAITING_CONFIRMATION task status."""

    def test_requires_confirmation_step_produces_waiting_state(self):
        """A task with requires_confirmation=True on step 1 must stop at WAITING_CONFIRMATION."""
        from agent.task_engine import execute_task
        from agent.database import update_task_state, get_task_state
        from datetime import datetime

        now_iso = datetime.utcnow().isoformat()
        conv_id = "conv_confirm_test_621"
        task = {
            "task_id": "task_confirm_621",
            "conversation_id": conv_id,
            "original_request": "shutdown my computer",
            "goal": "shutdown my computer",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": "Shutdown computer (REQUIRES CONFIRMATION)",
                    "tool": "open_application",
                    "arguments": {"app_name": "notepad"},
                    "status": "PENDING",
                    "result": None,
                    "error": None,
                    "requires_confirmation": True,
                    "started_at": None,
                    "completed_at": None
                }
            ],
            "created_at": now_iso,
            "updated_at": now_iso
        }
        update_task_state(conv_id, task)
        result = execute_task(task)
        self.assertEqual(result["status"], "WAITING_CONFIRMATION",
                         f"Expected WAITING_CONFIRMATION but got {result['status']}")


# ─── Test Group N: Context Clarification Hotfix (v6.2.1a) ────────────────────

class TestContextClarificationHotfix(unittest.TestCase):
    """
    Tests for the pending-clarification state, priority order, and previous conversation handling.
    Reproduces the exact real-world scenario and verifies context recovery.
    """

    def setUp(self):
        from app import app
        self.client = app.test_client()

    def test_01_real_world_reproduction_legion_to_loq(self):
        """
        TEST 1:
        User asks about ambiguous Legion.
        Assistant asks geographic clarification.
        Then user changes subject: 'Lenovo LOQ laptop' / 'Lenovo Lock Legion laptop'
        Assistant asks: 'Did you mean Lenovo LOQ laptop?'
        Then: 'Yes'
        Expected: LOQ candidate confirmed.
        Expected: NO geographic Legion clarification.
        """
        import uuid
        conv_id = f"test_legion_loq_{uuid.uuid4().hex[:8]}"

        # Turn 1: User asks about Legion, assistant asks geographic clarification
        from agent.database import add_message
        add_message(conv_id, "user", "Tell me about the NNW of Legion.")
        add_message(conv_id, "assistant", "Which Legion are you referring to? Could you clarify the geographic location?")

        # Turn 2: User says "No no no I am talking and asking about Lenovo Lock Legion laptop."
        # This matches Lenovo + Lock, producing clarification
        res2 = self.client.post('/api/chat', json={
            'message': 'No no no I am talking and asking about Lenovo Lock Legion laptop.',
            'conversation_id': conv_id
        })
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        self.assertTrue(
            "did you mean" in data2['reply'].lower() and "loq" in data2['reply'].lower(),
            f"Expected LOQ clarification, got: {data2['reply']}"
        )

        # Turn 3: User says "Yes"
        res3 = self.client.post('/api/chat', json={
            'message': 'Yes',
            'conversation_id': conv_id
        })
        self.assertEqual(res3.status_code, 200)
        data3 = res3.get_json()
        reply3 = data3['reply'].lower()

        # Expected: LOQ candidate confirmed
        self.assertTrue(
            "lenovo loq" in reply3 or "loq" in reply3,
            f"Expected LOQ confirmed in reply, got: {data3['reply']}"
        )
        self.assertEqual(data3.get('resolved_query'), "Lenovo LOQ laptop")

        # Expected: NO geographic Legion clarification
        self.assertNotIn("geographic", reply3)
        self.assertNotIn("still unclear which", reply3)
        self.assertNotIn("which 'legion'", reply3)

    def test_02_pending_clarification_yes(self):
        """
        TEST 2:
        Pending clarification + 'Yes' -> resolved to candidate.
        """
        import uuid
        from agent.database import set_pending_clarification
        conv_id = f"test_yes_{uuid.uuid4().hex[:8]}"
        set_pending_clarification(conv_id, {
            "type": "entity_confirmation",
            "candidate": "Lenovo LOQ laptop",
            "prompt": "Did you mean the Lenovo LOQ laptop?",
            "conversation_id": conv_id
        })

        res = self.client.post('/api/chat', json={'message': 'Yes', 'conversation_id': conv_id})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("Lenovo LOQ laptop", data['reply'])
        self.assertEqual(data.get('route'), 'clarification_confirmed')

    def test_03_pending_clarification_no(self):
        """
        TEST 3:
        Pending clarification + 'No' -> candidate rejected, asks what user meant.
        """
        import uuid
        from agent.database import set_pending_clarification
        conv_id = f"test_no_{uuid.uuid4().hex[:8]}"
        set_pending_clarification(conv_id, {
            "type": "entity_confirmation",
            "candidate": "Lenovo LOQ laptop",
            "prompt": "Did you mean the Lenovo LOQ laptop?",
            "conversation_id": conv_id
        })

        res = self.client.post('/api/chat', json={'message': 'No', 'conversation_id': conv_id})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("Understood", data['reply'])
        self.assertEqual(data.get('route'), 'clarification_rejected')

    def test_04_pending_clarification_yes_thats_correct(self):
        """
        TEST 4:
        Pending clarification + "Yes, that's correct" -> confirmed.
        """
        import uuid
        from agent.database import set_pending_clarification
        conv_id = f"test_correct_{uuid.uuid4().hex[:8]}"
        set_pending_clarification(conv_id, {
            "type": "entity_confirmation",
            "candidate": "Lenovo LOQ laptop",
            "prompt": "Did you mean the Lenovo LOQ laptop?",
            "conversation_id": conv_id
        })

        res = self.client.post('/api/chat', json={'message': "Yes, that's correct", 'conversation_id': conv_id})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("Lenovo LOQ laptop", data['reply'])
        self.assertEqual(data.get('route'), 'clarification_confirmed')

    def test_05_conversation_isolation(self):
        """
        TEST 5:
        Conversation A has pending clarification.
        Conversation B sends 'Yes'.
        Expected: B must NOT inherit A's clarification.
        """
        import uuid
        from agent.database import set_pending_clarification
        conv_a = f"test_iso_A_{uuid.uuid4().hex[:8]}"
        conv_b = f"test_iso_B_{uuid.uuid4().hex[:8]}"

        set_pending_clarification(conv_a, {
            "type": "entity_confirmation",
            "candidate": "Lenovo LOQ laptop",
            "prompt": "Did you mean the Lenovo LOQ laptop?",
            "conversation_id": conv_a
        })

        # Conversation B says "Yes" without having any clarification pending
        res_b = self.client.post('/api/chat', json={'message': 'Yes', 'conversation_id': conv_b})
        self.assertEqual(res_b.status_code, 200)
        data_b = res_b.get_json()
        # B must NOT confirm Lenovo LOQ
        self.assertNotIn("Lenovo LOQ laptop", data_b.get('reply', ''))
        self.assertNotEqual(data_b.get('route'), 'clarification_confirmed')

    def test_06_new_chat_clears_pending_clarification(self):
        """
        TEST 6:
        New Chat (DELETE /api/conversations/<conv_id>) clears pending clarification.
        """
        import uuid
        from agent.database import set_pending_clarification, get_pending_clarification
        conv_id = f"test_clear_{uuid.uuid4().hex[:8]}"
        set_pending_clarification(conv_id, {
            "type": "entity_confirmation",
            "candidate": "Lenovo LOQ laptop",
            "prompt": "Did you mean the Lenovo LOQ laptop?",
            "conversation_id": conv_id
        })
        self.assertIsNotNone(get_pending_clarification(conv_id))

        del_res = self.client.delete(f'/api/conversations/{conv_id}')
        self.assertEqual(del_res.status_code, 200)
        self.assertIsNone(get_pending_clarification(conv_id))

    def test_07_previous_conversation_request_unique(self):
        """
        TEST 7A:
        'Give me the response for the previous conversation.'
        When uniquely resolvable: resolves it safely without web search.
        """
        import uuid
        from agent.database import add_message
        conv_id = f"test_prev_uniq_{uuid.uuid4().hex[:8]}"
        add_message(conv_id, "user", "What is the capital of Tamil Nadu?")
        add_message(conv_id, "assistant", "The capital of Tamil Nadu is Chennai.")

        res = self.client.post('/api/chat', json={
            'message': 'Hello, give me the response for the previous conversation.',
            'conversation_id': conv_id
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("Chennai", data['reply'])
        self.assertEqual(data.get('sources'), [])
        self.assertEqual(data.get('route'), 'previous_conversation_resolution')

    def test_08_previous_conversation_request_ambiguous(self):
        """
        TEST 7B:
        'Give me the response for the previous conversation.'
        When multiple distinct queries exist: asks concise clarification.
        Never falls back to unrelated web search.
        """
        import uuid
        from agent.database import add_message
        conv_id = f"test_prev_amb_{uuid.uuid4().hex[:8]}"
        add_message(conv_id, "user", "What is the capital of France?")
        add_message(conv_id, "assistant", "The capital of France is Paris.")
        add_message(conv_id, "user", "What is the weather in Chennai?")
        add_message(conv_id, "assistant", "It is 32C and sunny in Chennai.")

        res = self.client.post('/api/chat', json={
            'message': 'Give me the response for the previous conversation.',
            'conversation_id': conv_id
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("which previous request", data['reply'].lower())
        self.assertEqual(data.get('sources'), [])
        self.assertEqual(data.get('route'), 'previous_conversation_disambiguation')



class TestFinalAcceptanceFixes(unittest.TestCase):
    """
    Automated regression tests for S.P.I.D.Y v6.2.1 Final Acceptance Fixes.
    Verifies context resolution with history, weather city parsing, and strict lock punctuation/safety.
    """

    def setUp(self):
        from app import app
        self.client = app.test_client()

    def test_01_context_continuation_no_500(self):
        """1. 'What is machine learning?' -> 'Tell me more about it.' must not return 500."""
        import uuid
        from unittest.mock import MagicMock
        conv_id = f"test_cont_{uuid.uuid4().hex[:8]}"

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = 'Machine learning is a field of AI.'
        mock_resp.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value = mock_resp

        import app as app_module
        orig_client = app_module.groq_client
        app_module.groq_client = mock_client
        try:
            r1 = self.client.post('/api/chat', json={'message': 'What is machine learning?', 'conversation_id': conv_id})
            self.assertEqual(r1.status_code, 200)

            # Turn 2: continuation with pronoun 'it'
            mock_resp.choices[0].message.content = 'More specifically, machine learning uses statistical techniques.'
            r2 = self.client.post('/api/chat', json={'message': 'Tell me more about it.', 'conversation_id': conv_id})
            self.assertEqual(r2.status_code, 200, f"Turn 2 failed with 500: {r2.get_json()}")
            self.assertNotIn("unexpected error", r2.get_json().get("reply", "").lower())
        finally:
            app_module.groq_client = orig_client

    def test_02_existing_history_conversational_joke(self):
        """2. 'Tell me a joke' in session with existing history must not raise NameError / 500."""
        import uuid
        from unittest.mock import MagicMock
        from agent.database import add_message
        conv_id = f"test_joke_{uuid.uuid4().hex[:8]}"
        add_message(conv_id, "user", "Hello Spidey")
        add_message(conv_id, "assistant", "Hello! How can I help you today?")

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = 'Why did the chicken cross the road?'
        mock_resp.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value = mock_resp

        import app as app_module
        orig_client = app_module.groq_client
        app_module.groq_client = mock_client
        try:
            r = self.client.post('/api/chat', json={'message': 'Tell me a joke', 'conversation_id': conv_id})
            self.assertEqual(r.status_code, 200)
            self.assertIn("chicken", r.get_json().get("reply", "").lower())
        finally:
            app_module.groq_client = orig_client

    def test_03_existing_history_current_news(self):
        """3. 'Tell me the current news.' in session with existing history must not raise NameError / 500."""
        import uuid
        from unittest.mock import MagicMock
        from agent.database import add_message
        conv_id = f"test_news_{uuid.uuid4().hex[:8]}"
        add_message(conv_id, "user", "What time is it?")
        add_message(conv_id, "assistant", "It is 2:00 PM.")

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = 'Here are the current top headlines.'
        mock_resp.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value = mock_resp

        import app as app_module
        orig_client = app_module.groq_client
        app_module.groq_client = mock_client
        try:
            r = self.client.post('/api/chat', json={'message': 'Tell me the current news.', 'conversation_id': conv_id})
            self.assertEqual(r.status_code, 200)
            self.assertNotIn("unexpected error", r.get_json().get("reply", "").lower())
        finally:
            app_module.groq_client = orig_client

    def test_04_weather_generic_phrase_uses_default_location(self):
        """4. 'What's the weather?' must use default location Chennai, NOT 'what's the weather'."""
        from commands import parse_command
        result = parse_command("what's the weather")
        self.assertIsNotNone(result)
        text = result if isinstance(result, str) else result.get('message', '')
        self.assertNotIn("what's the weather!", text.lower())
        self.assertIn("chennai", text.lower())

    def test_05_weather_what_is_the_weather_today_default_location(self):
        """5. 'What is the weather today?' must use default location Chennai."""
        from commands import parse_command
        result = parse_command("what is the weather today")
        self.assertIsNotNone(result)
        text = result if isinstance(result, str) else result.get('message', '')
        self.assertNotIn("what is the weather", text.lower())
        self.assertIn("chennai", text.lower())

    def test_06_weather_explicit_location(self):
        """6. 'weather in London' must extract 'London' as location."""
        from commands import parse_command
        result = parse_command("weather in London")
        self.assertIsNotNone(result)
        text = result if isinstance(result, str) else result.get('message', '')
        self.assertIn("london", text.lower())

    def test_07_lock_my_computer(self):
        """7. 'Lock my computer' must trigger explicit lock safety route."""
        from app import is_explicit_safety_command
        self.assertTrue(is_explicit_safety_command("Lock my computer"))

    def test_08_lock_my_computer_with_period(self):
        """8. 'Lock my computer.' must trigger explicit lock safety route."""
        from app import is_explicit_safety_command
        self.assertTrue(is_explicit_safety_command("Lock my computer."))

    def test_09_please_lock_the_pc_with_period(self):
        """9. 'Please lock the pc.' must trigger explicit lock safety route."""
        from app import is_explicit_safety_command
        self.assertTrue(is_explicit_safety_command("Please lock the pc."))

    def test_10_lenovo_lock_laptop_must_not_lock(self):
        """10. 'Lenovo Lock laptop' MUST NOT trigger workstation lock."""
        from app import is_explicit_safety_command
        from commands import parse_command
        self.assertFalse(is_explicit_safety_command("Lenovo Lock laptop"))
        cmd_res = parse_command("Lenovo Lock laptop")
        # Must return clarification or None, NOT shutdown/lock
        if cmd_res:
            self.assertIn("did you mean", str(cmd_res).lower())

    def test_11_lenovo_loq_laptop_must_not_lock(self):
        """11. 'Lenovo LOQ laptop' MUST NOT trigger workstation lock."""
        from app import is_explicit_safety_command
        from commands import parse_command
        self.assertFalse(is_explicit_safety_command("Lenovo LOQ laptop"))
        cmd_res = parse_command("Lenovo LOQ laptop")
        self.assertNotEqual(cmd_res, "Workstation locked!")

    def test_12_lenovo_legion_laptop_must_not_lock(self):
        """12. 'Lenovo Legion laptop' MUST NOT trigger workstation lock."""
        from app import is_explicit_safety_command
        from commands import parse_command
        self.assertFalse(is_explicit_safety_command("Lenovo Legion laptop"))
        cmd_res = parse_command("Lenovo Legion laptop")
        self.assertNotEqual(cmd_res, "Workstation locked!")


if __name__ == "__main__":
    unittest.main(verbosity=2)



# ─── Test Group J: UI + Text Chat + Unicode Fixes ───────────────────────────

class TestUITextChatUnicodeFixes(unittest.TestCase):
    """
    Regression tests for v6.2.1 UI/Text-Chat/Unicode hotfix:
      - Bug 1: Typed chat uses same /api/chat schema as voice path
      - Bug 2: Whisper heard NOT in visible chat
      - Bug 3: No mojibake in HTML/JS source files
    """

    # ── Bug 1: request schema ──────────────────────────────────────────────

    def test_01_typed_chat_uses_message_field(self):
        """Typed chat sends {'message': ..., 'conversation_id': ...} to /api/chat."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'app.py')
        with open(path, encoding='utf-8') as f:
            source = f.read()
        self.assertIn("data.get('message'", source)

    def test_02_chat_endpoint_accepts_conversation_id(self):
        """The /api/chat endpoint reads conversation_id from JSON body."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'app.py')
        with open(path, encoding='utf-8') as f:
            source = f.read()
        self.assertIn("data.get('conversation_id'", source)

    def test_03_typed_chat_returns_valid_route(self):
        """'What is machine learning?' routes without raising an exception."""
        import unittest.mock as mock
        with mock.patch('agent.router.groq_circuit_breaker') as mock_cb:
            mock_cb.check_circuit.return_value = (False, '')
            mock_groq = mock.MagicMock()
            mock_response = mock.MagicMock()
            mock_response.choices[0].message.content = 'Machine learning is AI.'
            mock_response.choices[0].message.tool_calls = None
            mock_groq.chat.completions.create.return_value = mock_response
            from agent.router import route_conversation
            result = route_conversation('What is machine learning?', 'test_typed_01', mock_groq)
            self.assertIn('reply', result)
            self.assertNotIn('rejected', result.get('reply', '').lower())

    def test_04_typed_chat_about_nvidia(self):
        """Typed 'about Nvidia' routes without 400 error."""
        import unittest.mock as mock
        with mock.patch('agent.router.groq_circuit_breaker') as mock_cb:
            mock_cb.check_circuit.return_value = (False, '')
            mock_groq = mock.MagicMock()
            mock_response = mock.MagicMock()
            mock_response.choices[0].message.content = 'Nvidia is a semiconductor company.'
            mock_response.choices[0].message.tool_calls = None
            mock_groq.chat.completions.create.return_value = mock_response
            from agent.router import route_conversation
            result = route_conversation('about Nvidia', 'test_typed_02', mock_groq)
            self.assertIn('reply', result)
            self.assertNotIn('rejected', result.get('reply', '').lower())

    def test_05_typed_chat_tell_me_a_joke(self):
        """Typed 'Tell me a joke' routes and returns content."""
        import unittest.mock as mock
        with mock.patch('agent.router.groq_circuit_breaker') as mock_cb:
            mock_cb.check_circuit.return_value = (False, '')
            mock_groq = mock.MagicMock()
            mock_response = mock.MagicMock()
            mock_response.choices[0].message.content = 'Why did the chicken cross the road?'
            mock_response.choices[0].message.tool_calls = None
            mock_groq.chat.completions.create.return_value = mock_response
            from agent.router import route_conversation
            result = route_conversation('Tell me a joke', 'test_typed_03', mock_groq)
            self.assertIn('reply', result)
            self.assertNotIn('rejected', result.get('reply', '').lower())

    def test_06_router_turn2_updates_system_prompt(self):
        """router.py Turn 2 synthesis updates messages[0] to NOT call tools."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'agent', 'router.py')
        with open(path, encoding='utf-8') as f:
            source = f.read()
        self.assertIn('Do NOT call any more tools', source)
        self.assertIn('has been retrieved above', source)
        self.assertIn('messages[0] = {', source)

    def test_07_voice_and_typed_use_same_endpoint(self):
        """Both voice (Whisper) and typed paths call handleSend -> POST /api/chat."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'static', 'app.js')
        with open(path, encoding='utf-8') as f:
            js = f.read()
        self.assertIn("'/api/chat'", js)
        self.assertIn('await handleSend(transcript)', js)

    def test_08_conversation_id_preserved_in_js(self):
        """app.js sends conversationId with every /api/chat request."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'static', 'app.js')
        with open(path, encoding='utf-8') as f:
            js = f.read()
        self.assertIn('conversationId', js)
        self.assertIn('conversation_id', js)

    # ── Bug 2: Whisper heard not in chat UI ───────────────────────────────

    def test_09_whisper_heard_not_in_addmsg(self):
        """'Whisper heard' must NOT be passed to addMsg() in the visible chat UI."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'static', 'app.js')
        with open(path, encoding='utf-8') as f:
            js = f.read()
        for line in js.splitlines():
            if 'Whisper heard' in line and 'addMsg' in line:
                self.fail(f"addMsg must not contain 'Whisper heard': {line.strip()}")

    def test_10_whisper_heard_goes_to_console_log(self):
        """Whisper transcript is logged to browser console.log, not addMsg."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'static', 'app.js')
        with open(path, encoding='utf-8') as f:
            js = f.read()
        self.assertIn("Whisper heard", js)
        self.assertIn("console.log", js)
        for line in js.splitlines():
            if 'Whisper heard' in line:
                self.assertNotIn('addMsg', line, f"addMsg must not contain 'Whisper heard': {line}")
                self.assertIn('console.log', line, f"console.log must log 'Whisper heard': {line}")

    # ── Bug 3: Unicode / encoding ──────────────────────────────────────────

    def test_11_html_declares_utf8_charset(self):
        """SPIDY.html must declare charset=UTF-8 in <meta> tag."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'static', 'SPIDY.html')
        with open(path, encoding='utf-8') as f:
            html = f.read()
        self.assertIn('<meta charset="UTF-8"', html)

    def test_12_no_em_dash_mojibake_in_html(self):
        """SPIDY.html must not contain corrupted em-dash bytes (mojibake)."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'static', 'SPIDY.html')
        with open(path, encoding='utf-8') as f:
            html = f.read()
        # U+00E2 U+20AC U+201D = the mojibake for em dash
        self.assertNotIn('\u00e2\u20ac\u201d', html, "Mojibake for em-dash found in SPIDY.html")
        self.assertNotIn('\u00e2\u20ac\u201c', html, "Mojibake for en-dash found in SPIDY.html")

    def test_13_no_emoji_mojibake_in_html(self):
        """SPIDY.html must not contain corrupted 4-byte emoji prefix (mojibake)."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'static', 'SPIDY.html')
        with open(path, encoding='utf-8') as f:
            html = f.read()
        # U+00F0 U+0178 = the mojibake prefix for 4-byte emoji
        self.assertNotIn('\u00f0\u0178', html, "Mojibake emoji prefix found in SPIDY.html")

    def test_14_no_em_dash_mojibake_in_js(self):
        """static/app.js must not contain corrupted em-dash bytes."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'static', 'app.js')
        with open(path, encoding='utf-8') as f:
            js = f.read()
        self.assertNotIn('\u00e2\u20ac\u201d', js, "Mojibake em-dash found in app.js")
        self.assertNotIn('\u00e2\u20ac\u201c', js, "Mojibake en-dash found in app.js")

    def test_15_no_emoji_mojibake_in_js(self):
        """static/app.js must not contain corrupted 4-byte emoji prefix."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'static', 'app.js')
        with open(path, encoding='utf-8') as f:
            js = f.read()
        self.assertNotIn('\u00f0\u0178\u017d', js, "Mojibake microphone emoji found in app.js")

    def test_16_html_is_valid_utf8(self):
        """SPIDY.html is a valid UTF-8 file with no illegal byte sequences."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'static', 'SPIDY.html')
        with open(path, 'rb') as f:
            data = f.read()
        try:
            data.decode('utf-8')
        except UnicodeDecodeError as e:
            self.fail(f"SPIDY.html is not valid UTF-8: {e}")

    def test_17_js_is_valid_utf8(self):
        """static/app.js is a valid UTF-8 file."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'static', 'app.js')
        with open(path, 'rb') as f:
            data = f.read()
        try:
            data.decode('utf-8')
        except UnicodeDecodeError as e:
            self.fail(f"app.js is not valid UTF-8: {e}")

    def test_18_html_ready_string_no_mojibake(self):
        """SPIDY.html 'Ready' string has correct dash, not mojibake."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'static', 'SPIDY.html')
        with open(path, encoding='utf-8') as f:
            html = f.read()
        self.assertIn('System Commands Active', html)
        idx = html.find('Ready')
        if idx != -1:
            snippet = html[idx:idx + 40]
            self.assertNotIn('\u00e2\u20ac', snippet, f"Mojibake in Ready string: {repr(snippet)}")

    def test_19_flask_json_as_ascii_disabled(self):
        """Flask is configured JSON_AS_ASCII=False so emoji in replies are not escaped."""
        import os
        path = os.path.join(os.path.dirname(__file__), 'app.py')
        with open(path, encoding='utf-8') as f:
            source = f.read()
        self.assertIn("JSON_AS_ASCII", source)
        # Must be set to False
        idx = source.find("JSON_AS_ASCII")
        self.assertIn('False', source[idx:idx + 30])
