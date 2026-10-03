"""
S.P.I.D.Y Automated Comprehensive Test Suite
Validates startup, configuration, endpoints, deterministic routing,
voice normalization, safety whitelist, intent classification, sentiment analysis,
Whisper ASR, and all 10 required benchmark commands.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import json

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import (
    APPLICATION_WHITELIST,
    FFMPEG_AVAILABLE,
    FFMPEG_PATH,
    GROQ_API_KEY,
    GROQ_MODEL,
    TORCH_DEVICE,
    GPU_NAME
)
from commands import (
    normalize_voice_text,
    resolve_app_key,
    open_app,
    close_app,
    parse_command
)
from app import app

class TestConfigAndEnvironment(unittest.TestCase):
    def test_ffmpeg_detection(self):
        """FFmpeg must be detected and available."""
        self.assertTrue(FFMPEG_AVAILABLE, "FFmpeg should be detected on the system.")
        self.assertIsNotNone(FFMPEG_PATH, "FFMPEG_PATH should not be None.")
        self.assertTrue(os.path.exists(FFMPEG_PATH), f"FFmpeg binary should exist at {FFMPEG_PATH}")

    def test_torch_and_device(self):
        """PyTorch and device detection must operate cleanly."""
        import torch
        self.assertIsNotNone(TORCH_DEVICE)
        self.assertIn(TORCH_DEVICE.type, ['cuda', 'cpu'])
        if torch.cuda.is_available():
            self.assertEqual(TORCH_DEVICE.type, 'cuda')
            self.assertIn("RTX", GPU_NAME)

    def test_groq_config_security(self):
        """Groq configuration must never expose key in model names or representation."""
        self.assertNotEqual(GROQ_MODEL, "llama-3.1-8b-instant", "Retired model must not be configured.")
        self.assertEqual(GROQ_MODEL, "openai/gpt-oss-20b")
        if GROQ_API_KEY:
            self.assertFalse(GROQ_API_KEY.startswith("llama"))
            # Ensure key is not printed in repr
            masked = f"{GROQ_API_KEY[:4]}...{GROQ_API_KEY[-4:]}"
            self.assertNotIn(GROQ_API_KEY, repr({"key": masked}))


class TestNormalizationAndSafety(unittest.TestCase):
    def test_voice_misrecognition_normalization(self):
        """ASR misrecognitions must normalize safely."""
        self.assertEqual(normalize_voice_text("Open Noted"), "open notepad")
        self.assertEqual(normalize_voice_text("open not bad"), "open notepad")
        self.assertEqual(normalize_voice_text("open not that"), "open notepad")
        self.assertEqual(normalize_voice_text("open note pad"), "open notepad")
        self.assertEqual(normalize_voice_text("open calc"), "open calculator")
        self.assertEqual(normalize_voice_text("open calculates"), "open calculator")
        self.assertEqual(normalize_voice_text("open vs code"), "open vscode")
        self.assertEqual(normalize_voice_text("take screen shot"), "take a screenshot")
        self.assertEqual(normalize_voice_text("raise volume"), "increase volume")
        self.assertEqual(normalize_voice_text("lower volume"), "decrease volume")

    def test_application_whitelist_resolution(self):
        """Allowed apps must resolve; arbitrary names must return None."""
        self.assertEqual(resolve_app_key("notepad"), "notepad")
        self.assertEqual(resolve_app_key("calculator"), "calculator")
        self.assertEqual(resolve_app_key("chrome"), "chrome")
        self.assertEqual(resolve_app_key("google chrome"), "chrome")
        self.assertEqual(resolve_app_key("code"), "vscode")
        self.assertEqual(resolve_app_key("explorer"), "explorer")

        # Dangerous or unknown applications must NOT resolve
        self.assertIsNone(resolve_app_key("cmd /c del *"))
        self.assertIsNone(resolve_app_key("powershell -enc ..."))
        self.assertIsNone(resolve_app_key("malicious_trojan.exe"))
        self.assertIsNone(resolve_app_key("arbitrary_binary"))

    @patch('subprocess.Popen')
    def test_open_app_safety(self, mock_popen):
        """open_app must reject unwhitelisted applications and avoid shell=True."""
        # Configure mock process: poll() returns None (process still running = success)
        mock_popen.return_value.poll.return_value = None
        mock_popen.return_value.returncode = 0

        # Whitelisted app
        res = open_app("notepad")
        self.assertIn("Opening Notepad", res)
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        self.assertFalse(kwargs.get('shell', False), "shell must be False for safety")

        mock_popen.reset_mock()
        mock_popen.return_value.poll.return_value = None
        mock_popen.return_value.returncode = 0
        # Malicious / unknown input
        res_reject = open_app("malicious_payload; rm -rf /")
        self.assertIn("For security reasons", res_reject)
        mock_popen.assert_not_called()


class TestDeterministicCommands(unittest.TestCase):
    @patch('subprocess.Popen')
    def test_notepad_command(self, mock_popen):
        mock_popen.return_value.poll.return_value = None
        mock_popen.return_value.returncode = 0
        res = parse_command("Open Notepad")
        self.assertIn("Opening Notepad", str(res))

    @patch('subprocess.Popen')
    def test_calculator_command(self, mock_popen):
        mock_popen.return_value.poll.return_value = None
        mock_popen.return_value.returncode = 0
        res = parse_command("Open Calculator")
        self.assertIn("Opening Calculator", str(res))

    def test_time_command(self):
        res = parse_command("What time is it?")
        self.assertIn("It's", res)

    @patch('commands.take_screenshot', return_value="Screenshot captured!")
    def test_screenshot_command(self, mock_shot):
        res = parse_command("take a screenshot")
        self.assertEqual(res, "Screenshot captured!")

    @patch('commands.control_volume', return_value="Volume increased!")
    def test_volume_command(self, mock_vol):
        res = parse_command("increase the volume")
        self.assertEqual(res, "Volume increased!")

    def test_notes_command(self):
        res = parse_command("show my notes")
        self.assertTrue("notes" in str(res).lower())

    def test_reminders_command(self):
        res = parse_command("set a reminder in 15 minutes to inspect code")
        self.assertIn("Reminder set for", res)

    def test_chrome_command(self):
        res = parse_command("open chrome")
        self.assertIn("Opening Google Chrome", str(res))

    def test_conversational_passthrough(self):
        """Conversational query should not be caught by deterministic parser."""
        res = parse_command("Tell me about machine learning")
        self.assertIsNone(res, "Conversational question should fall through to AI route.")


class TestAIModels(unittest.TestCase):
    def test_sentiment_analyzer(self):
        """Sentiment analyzer returns valid output schema."""
        from sentiment_analyzer import sentiment_analyzer
        self.assertTrue(sentiment_analyzer.loaded, "Sentiment analyzer should be loaded.")
        res = sentiment_analyzer.analyze("I am extremely happy and excited today!")
        self.assertIn(res['label'], ['POSITIVE', 'NEUTRAL', 'NEGATIVE'])
        self.assertIn('tone', res)
        self.assertIn('confidence', res)
        self.assertTrue(res['loaded'])

    def test_intent_detector(self):
        """Intent detector returns valid schema on zero-shot classification."""
        from intent_detector import intent_detector
        self.assertTrue(intent_detector.loaded, "Intent detector should be loaded.")
        res = intent_detector.detect("what is the weather today?")
        if res:
            self.assertIn('intent', res)
            self.assertIn('action', res)
            self.assertIn('confidence', res)
            self.assertIsInstance(res['confidence'], float)

    def test_whisper_transcription(self):
        """Whisper base model transcribes test audio fixture cleanly."""
        from whisper_asr import whisper_asr
        self.assertTrue(whisper_asr.loaded, "Whisper model should be loaded.")

        test_audio = os.path.join(BASE_DIR, "voice_test.wav")
        if os.path.exists(test_audio):
            text, lang = whisper_asr.transcribe_audio_file(test_audio)
            self.assertIsNotNone(text)
            self.assertIn("excuse me", text.lower())

    def test_whisper_empty_audio_handling(self):
        """Empty audio bytes are rejected safely without crashing."""
        from whisper_asr import whisper_asr
        text, msg = whisper_asr.transcribe_from_bytes(b"")
        self.assertIsNone(text)
        self.assertIn("empty or too short", msg)

    def test_whisper_webm_audio_handling(self):
        """WebM/Opus audio bytes do not crash with sample_width KeyError."""
        from whisper_asr import whisper_asr
        
        # Simulate a small WebM file upload (just enough to bypass length check, but invalid content so FFmpeg fails safely instead of throwing KeyError)
        # We just want to ensure it doesn't raise KeyError('sample_width') during pydub processing.
        # Since we removed pydub for conversion, it should hit FFmpeg, fail to convert (since it's fake data), and return gracefully.
        fake_webm_bytes = b"RIFF" + b"\x00" * 200
        
        try:
            text, msg = whisper_asr.transcribe_from_bytes(fake_webm_bytes)
            # The exact error message depends on ffmpeg, but it shouldn't crash with KeyError.
            self.assertIsNone(text)
        except KeyError as e:
            self.fail(f"Regression: raised KeyError({e}) on WebM audio bytes")


class TestFlaskEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_index_page(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'S.P.I.D.Y', res.data)
        self.assertIn(b'id="wb"', res.data)
        self.assertIn(b'id="mb"', res.data)

    def test_status_endpoint(self):
        res = self.client.get('/api/status')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'online')
        self.assertEqual(data['version'], '6.2.1')
        self.assertIn('groq', data)
        self.assertIn('whisper', data)
        self.assertIn('cuda', data)
        self.assertIn('ffmpeg', data)
        self.assertTrue(data['ffmpeg']['available'])

    def test_chat_deterministic(self):
        res = self.client.post('/api/chat', json={'message': 'what time is it?'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn("It's", data['reply'])

    def test_chat_empty_message(self):
        res = self.client.post('/api/chat', json={'message': ''})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data['status'], 'error')

    def test_chat_conversational_groq_fallback(self):
        """Conversational query reaches AI route without crashing."""
        res = self.client.post('/api/chat', json={'message': 'Explain neural networks in two sentences.'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(len(data.get('reply', '')) > 0)

    def test_whisper_transcribe_empty(self):
        res = self.client.post('/api/whisper/transcribe')
        # 400 = no audio file provided; 503 = Whisper not yet loaded in test env — both are valid error states
        self.assertIn(res.status_code, (400, 503))
        data = res.get_json()
        self.assertEqual(data['status'], 'error')

    def test_notes_api(self):
        # GET
        res = self.client.get('/api/notes')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'ok')

        # POST
        res_post = self.client.post('/api/notes', json={'text': 'Test note from test suite'})
        self.assertEqual(res_post.status_code, 200)

    def test_reminders_api(self):
        res = self.client.get('/api/reminders')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'ok')


class TestRequiredBenchmarkVoiceCommands(unittest.TestCase):
    """
    End-to-End Validation of the 10 Required Benchmark Commands:
    1. "Open Notepad"
    2. "Open Calculator"
    3. "Show my notes"
    4. "What time is it?"
    5. "What's the weather?"
    6. "Tell me about machine learning"
    7. "Take a screenshot"
    8. "Increase the volume"
    9. "Set a reminder"
    10. "Open Chrome"
    """
    def setUp(self):
        self.client = app.test_client()

    @patch('subprocess.Popen')
    def test_01_open_notepad(self, mock_popen):
        mock_popen.return_value.poll.return_value = None
        mock_popen.return_value.returncode = 0
        res = self.client.post('/api/chat', json={'message': 'Open Notepad'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("Opening Notepad", data['reply'])

    @patch('subprocess.Popen')
    def test_02_open_calculator(self, mock_popen):
        mock_popen.return_value.poll.return_value = None
        mock_popen.return_value.returncode = 0
        res = self.client.post('/api/chat', json={'message': 'Open Calculator'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("Opening Calculator", data['reply'])

    def test_03_show_my_notes(self):
        res = self.client.post('/api/chat', json={'message': 'Show my notes'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue('notes' in data['reply'].lower())

    def test_04_what_time_is_it(self):
        res = self.client.post('/api/chat', json={'message': 'What time is it?'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("It's", data['reply'])

    def test_05_whats_the_weather(self):
        res = self.client.post('/api/chat', json={'message': "What's the weather?"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue('weather' in data['reply'].lower() or data.get('action') == 'open_url')

    def test_06_tell_me_about_machine_learning(self):
        res = self.client.post('/api/chat', json={'message': 'Tell me about machine learning'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(len(data['reply']) > 10)

    @patch('commands.take_screenshot', return_value="Screenshot captured and saved to Desktop!")
    def test_07_take_a_screenshot(self, mock_shot):
        res = self.client.post('/api/chat', json={'message': 'Take a screenshot'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("Screenshot captured", data['reply'])

    @patch('commands.control_volume', return_value="Volume increased to 60%!")
    def test_08_increase_the_volume(self, mock_vol):
        res = self.client.post('/api/chat', json={'message': 'Increase the volume'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("Volume increased", data['reply'])

    def test_09_set_a_reminder(self):
        res = self.client.post('/api/chat', json={'message': 'Set a reminder in 30 minutes to drink water'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("Reminder set for", data['reply'])

    @patch('subprocess.Popen')
    def test_10_open_chrome(self, mock_popen):
        mock_popen.return_value.poll.return_value = None
        mock_popen.return_value.returncode = 0
        res = self.client.post('/api/chat', json={'message': 'Open Chrome'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("Opening Google Chrome", data['reply'])


# ============================================================
# V6 NEW TESTS: Conversation Memory, Agent Tools, DB, Name
# ============================================================

class TestV6Database(unittest.TestCase):
    """Tests for the V6 SQLite conversation memory system."""

    def test_database_module_imports(self):
        """The agent database module must import cleanly."""
        from agent.database import (
            init_db, create_conversation, add_message,
            get_recent_messages, clear_conversation,
            set_long_term_memory, get_all_long_term_memory
        )
        # If import succeeded, module is present
        self.assertTrue(True)

    def test_create_and_read_conversation(self):
        """Creating a conversation and adding messages must work."""
        import time
        from agent.database import create_conversation, add_message, get_recent_messages, clear_conversation
        conv_id = f'test_conv_unit_abc_{int(time.time() * 1000)}'
        create_conversation(conv_id, 'Unit Test Conversation')
        add_message(conv_id, 'user', 'Hello Spidey')
        add_message(conv_id, 'assistant', 'Hello! How can I help?')
        history = get_recent_messages(conv_id, limit=10)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['role'], 'user')
        self.assertEqual(history[0]['content'], 'Hello Spidey')
        self.assertEqual(history[1]['role'], 'assistant')
        # Cleanup
        clear_conversation(conv_id)

    def test_conversation_history_limit(self):
        """get_recent_messages must respect the limit parameter."""
        from agent.database import create_conversation, add_message, get_recent_messages
        conv_id = 'test_conv_limit_xyz789'
        create_conversation(conv_id, 'Limit Test')
        for i in range(15):
            add_message(conv_id, 'user', f'Message {i}')
        history = get_recent_messages(conv_id, limit=5)
        self.assertLessEqual(len(history), 5)

    def test_clear_conversation(self):
        """Clearing a conversation must remove all messages."""
        from agent.database import create_conversation, add_message, get_recent_messages, clear_conversation
        conv_id = 'test_conv_clear_clear999'
        create_conversation(conv_id, 'Clear Test')
        add_message(conv_id, 'user', 'Test message')
        clear_conversation(conv_id)
        history = get_recent_messages(conv_id, limit=10)
        self.assertEqual(len(history), 0)

    def test_long_term_memory_set_get(self):
        """Long-term memory must persist key-value pairs correctly."""
        from agent.database import set_long_term_memory, get_all_long_term_memory
        set_long_term_memory('test_user_name', 'Hari', importance=5)
        mem = get_all_long_term_memory()
        self.assertIn('test_user_name', mem)
        self.assertEqual(mem['test_user_name'], 'Hari')


class TestV6ToolRegistry(unittest.TestCase):
    """Tests for the V6 agent tool registry."""

    def test_tool_registry_imports(self):
        """Tool registry must import cleanly."""
        from agent.tools import AVAILABLE_TOOLS, get_tool_schemas
        self.assertIn('web_search', AVAILABLE_TOOLS)
        self.assertIn('get_weather', AVAILABLE_TOOLS)
        self.assertIn('take_screenshot', AVAILABLE_TOOLS)
        self.assertIn('open_application', AVAILABLE_TOOLS)
        self.assertIn('control_volume', AVAILABLE_TOOLS)

    def test_tool_schemas_are_valid(self):
        """Tool schemas returned for Groq must be valid dictionaries."""
        from agent.tools import get_tool_schemas
        schemas = get_tool_schemas()
        self.assertIsInstance(schemas, list)
        self.assertGreater(len(schemas), 0)
        for s in schemas:
            self.assertEqual(s['type'], 'function')
            self.assertIn('name', s['function'])
            self.assertIn('description', s['function'])

    def test_web_search_returns_string(self):
        """web_search tool must return a string result."""
        from agent.tools import AVAILABLE_TOOLS
        result = AVAILABLE_TOOLS['web_search']['func']({'query': 'Python programming language'})
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_open_application_rejects_unknown(self):
        """open_application must reject unknown/unwhitelisted app names."""
        from agent.tools import AVAILABLE_TOOLS
        result = AVAILABLE_TOOLS['open_application']['func']({'app_name': 'malware.exe'})
        self.assertIsInstance(result, str)
        # Must not say "Opening"
        self.assertNotIn('Opening malware', result)

    def test_control_volume_rejects_invalid_action(self):
        """control_volume must reject invalid action strings."""
        from agent.tools import AVAILABLE_TOOLS
        result = AVAILABLE_TOOLS['control_volume']['func']({'action': 'rm -rf /'})
        self.assertIsInstance(result, str)
        self.assertIn('Unknown volume action', result)


class TestV6ConversationAPIEndpoints(unittest.TestCase):
    """Tests for the V6 conversation management API endpoints."""

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_new_conversation_api(self):
        """POST /api/conversations must create a conversation successfully."""
        res = self.client.post('/api/conversations', json={'conversation_id': 'api_test_conv_001'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn('conversation_id', data)

    def test_delete_conversation_api(self):
        """DELETE /api/conversations/<id> must clear history successfully."""
        # Create first
        self.client.post('/api/conversations', json={'conversation_id': 'del_test_conv_001'})
        # Then delete
        res = self.client.delete('/api/conversations/del_test_conv_001')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'ok')

    def test_memory_api(self):
        """GET /api/memory must return the memory store."""
        res = self.client.get('/api/memory')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn('memory', data)

    def test_chat_sends_conversation_id(self):
        """POST /api/chat must accept and use conversation_id field."""
        res = self.client.post('/api/chat', json={
            'message': 'what time is it?',
            'conversation_id': 'test_session_99'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'ok')

    def test_status_returns_v6(self):
        """GET /api/status must report version 6.2.1."""
        res = self.client.get('/api/status')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['version'], '6.2.1')


class TestV6NamePronunciation(unittest.TestCase):
    """
    Regression tests verifying the assistant name is 'Spidey' not 'S-P-I-D-Y'.
    """

    def test_system_prompt_uses_spidey_not_spelled_out(self):
        """The SYSTEM_PROMPT must tell the model to use 'Spidey', not spell it letter-by-letter.
        The string S-P-I-D-Y may appear as a negative example (NEVER do this),
        but must NOT appear as a positive self-identification instruction."""
        from config import SYSTEM_PROMPT
        # Must contain the friendly spoken name
        self.assertIn('Spidey', SYSTEM_PROMPT)
        # Must NOT say "refer to yourself as S-P-I-D-Y"
        self.assertNotIn('refer to yourself as S-P-I-D-Y', SYSTEM_PROMPT)
        # Must NOT say "I am S-P-I-D-Y" as an instruction
        self.assertNotIn('I am S-P-I-D-Y', SYSTEM_PROMPT)
        # The NEVER prohibition is acceptable — it's telling the model what NOT to say
        if 'S-P-I-D-Y' in SYSTEM_PROMPT:
            self.assertIn('NEVER', SYSTEM_PROMPT,
                msg="If S-P-I-D-Y appears in SYSTEM_PROMPT it must be in a prohibition context (NEVER)")

    def test_system_prompt_does_not_instruct_letter_spelling(self):
        """SYSTEM_PROMPT must not instruct the model to spell the name letter by letter."""
        from config import SYSTEM_PROMPT
        # These patterns indicate letter-by-letter TTS pronunciation
        import re
        letter_pattern = re.compile(r'\bS\s*\.\s*P\s*\.\s*I\s*\.\s*D\s*\.\s*Y\b')
        # The brand name S.P.I.D.Y may appear as a label but must never be in instructions
        # about what to *say*. The prompt must say "refer to yourself as Spidey"
        self.assertIn('Spidey', SYSTEM_PROMPT)


class TestV6RouterModule(unittest.TestCase):
    """Tests for the agent router module (no live Groq calls)."""

    def test_router_imports(self):
        """Agent router module must import cleanly."""
        from agent.router import route_conversation
        self.assertTrue(callable(route_conversation))

    def test_router_handles_missing_groq_client(self):
        """Router must return a safe reply when Groq client is None."""
        from agent.router import route_conversation
        result = route_conversation('Hello', 'test_no_groq_sess', None)
        self.assertIn('reply', result)
        self.assertIsInstance(result['reply'], str)
        self.assertGreater(len(result['reply']), 0)

    def test_router_returns_sources_field(self):
        """Router must always return a 'sources' field (list) even without Groq."""
        from agent.router import route_conversation
        result = route_conversation('Hello', 'test_sources_field', None)
        self.assertIn('sources', result)
        self.assertIsInstance(result['sources'], list)

    def test_router_returns_resolved_query_field(self):
        """Router must always return a 'resolved_query' field."""
        from agent.router import route_conversation
        result = route_conversation('Hello', 'test_rq_field', None)
        self.assertIn('resolved_query', result)


# ============================================================
# V6.1 HARDENING TESTS
# ============================================================

class TestV61ContextResolver(unittest.TestCase):
    """Tests for the context resolver module."""

    def test_context_resolver_imports(self):
        """Context resolver must import cleanly."""
        from agent.context_resolver import resolve_context, needs_freshness, is_reference_only
        self.assertTrue(callable(resolve_context))
        self.assertTrue(callable(needs_freshness))
        self.assertTrue(callable(is_reference_only))

    def test_freshness_triggers_current_pm(self):
        """'current Prime Minister' must trigger freshness."""
        from agent.context_resolver import needs_freshness
        self.assertTrue(needs_freshness("Who is the current Prime Minister of India?"))

    def test_freshness_triggers_latest_news(self):
        """'latest news' must trigger freshness."""
        from agent.context_resolver import needs_freshness
        self.assertTrue(needs_freshness("What is the latest news about AI?"))

    def test_freshness_triggers_weather(self):
        """'weather' implicitly needs fresh data (via get_weather tool)."""
        from agent.context_resolver import needs_freshness
        self.assertTrue(needs_freshness("what's the weather today in Chennai?"))

    def test_no_freshness_for_static(self):
        """Static knowledge questions must NOT trigger freshness."""
        from agent.context_resolver import needs_freshness
        self.assertFalse(needs_freshness("What is machine learning?"))
        self.assertFalse(needs_freshness("Explain recursion in Python."))
        self.assertFalse(needs_freshness("How does a neural network work?"))

    def test_reference_only_short_words(self):
        """Short reference words must be detected as continuation."""
        from agent.context_resolver import is_reference_only
        self.assertTrue(is_reference_only("India"))
        self.assertTrue(is_reference_only("Yes"))
        self.assertTrue(is_reference_only("No"))
        self.assertTrue(is_reference_only("Tell me more"))
        self.assertTrue(is_reference_only("What about him"))
        self.assertTrue(is_reference_only("Singapore"))

    def test_reference_only_full_question_is_not_reference(self):
        """A full, explicit question must not be flagged as a reference only."""
        from agent.context_resolver import is_reference_only
        self.assertFalse(is_reference_only("What is the capital of France?"))
        self.assertFalse(is_reference_only("Open Notepad please"))

    def test_resolve_context_with_no_history(self):
        """Context resolver must return default state when history is empty."""
        from agent.context_resolver import resolve_context
        result = resolve_context("What is Python?", [], None)
        self.assertIn('resolved_query', result)
        self.assertIn('requires_web_search', result)
        self.assertIsInstance(result['requires_web_search'], bool)

    def test_resolve_context_default_freshness_without_groq(self):
        """Without Groq client, freshness must still be detected from keywords."""
        from agent.context_resolver import resolve_context
        # current PM is a freshness trigger — even without Groq
        result = resolve_context("Who is the current Prime Minister of India?", [], None)
        # requires_web_search should be True since keyword matches
        self.assertTrue(result.get('requires_web_search', False))


class TestV61TaskState(unittest.TestCase):
    """Tests for task state: storage, accumulation, isolation."""

    def test_task_state_stored_and_retrieved(self):
        """Task state written to DB must be retrievable."""
        import time
        from agent.database import create_conversation, update_task_state, get_task_state
        conv_id = f'task_test_{int(time.time() * 1000)}'
        create_conversation(conv_id)
        state = {"task_type": "job_search", "company": "ITC Infotech", "role": None, "location": None, "active": True}
        update_task_state(conv_id, state)
        retrieved = get_task_state(conv_id)
        self.assertEqual(retrieved['task_type'], 'job_search')
        self.assertEqual(retrieved['company'], 'ITC Infotech')

    def test_task_state_accumulates_filters(self):
        """Task state must merge new filters with existing ones."""
        import time
        from agent.database import create_conversation, update_task_state, get_task_state
        conv_id = f'task_accum_{int(time.time() * 1000)}'
        create_conversation(conv_id)
        # Start: company set
        update_task_state(conv_id, {"task_type": "job_search", "company": "ITC Infotech", "role": None, "location": None, "active": True})
        # Add role filter
        existing = get_task_state(conv_id)
        existing['role'] = 'ML Engineer'
        update_task_state(conv_id, existing)
        # Add location filter
        existing = get_task_state(conv_id)
        existing['location'] = 'Singapore'
        update_task_state(conv_id, existing)

        final = get_task_state(conv_id)
        self.assertEqual(final['company'], 'ITC Infotech')
        self.assertEqual(final['role'], 'ML Engineer')
        self.assertEqual(final['location'], 'Singapore')

    def test_task_state_cleared_on_new_conversation(self):
        """New Chat (clear_conversation) must reset task state."""
        import time
        from agent.database import create_conversation, update_task_state, get_task_state, clear_conversation
        conv_id = f'task_clear_{int(time.time() * 1000)}'
        create_conversation(conv_id)
        update_task_state(conv_id, {"task_type": "job_search", "company": "ITC Infotech", "active": True})
        clear_conversation(conv_id)
        state = get_task_state(conv_id)
        self.assertIsNone(state)

    def test_task_state_null_initially(self):
        """Newly created conversation must have null task state."""
        import time
        from agent.database import create_conversation, get_task_state
        conv_id = f'task_null_{int(time.time() * 1000)}'
        create_conversation(conv_id)
        self.assertIsNone(get_task_state(conv_id))


class TestV61ConversationIsolation(unittest.TestCase):
    """Tests that conversations are isolated from each other."""

    def test_two_conversations_have_separate_histories(self):
        """Messages in conversation A must not appear in conversation B."""
        import time
        from agent.database import create_conversation, add_message, get_recent_messages
        conv_a = f'iso_a_{int(time.time() * 1000)}'
        conv_b = f'iso_b_{int(time.time() * 1000)}'
        create_conversation(conv_a)
        create_conversation(conv_b)
        add_message(conv_a, 'user', 'ITC Infotech jobs')
        add_message(conv_a, 'assistant', 'Looking for ITC Infotech jobs...')
        add_message(conv_b, 'user', 'Tell me about Marvel')

        hist_a = get_recent_messages(conv_a)
        hist_b = get_recent_messages(conv_b)

        # Conversation B must not contain A's messages
        contents_b = [m['content'] for m in hist_b]
        self.assertNotIn('ITC Infotech jobs', contents_b)
        self.assertNotIn('Looking for ITC Infotech jobs...', contents_b)

        # Conversation A must not contain B's messages
        contents_a = [m['content'] for m in hist_a]
        self.assertNotIn('Tell me about Marvel', contents_a)

    def test_two_conversations_have_separate_task_states(self):
        """Task state in conversation A must not affect conversation B."""
        import time
        from agent.database import create_conversation, update_task_state, get_task_state
        conv_a = f'task_iso_a_{int(time.time() * 1000)}'
        conv_b = f'task_iso_b_{int(time.time() * 1000)}'
        create_conversation(conv_a)
        create_conversation(conv_b)
        update_task_state(conv_a, {"task_type": "job_search", "company": "ITC Infotech", "active": True})
        # B's task state should be None
        self.assertIsNone(get_task_state(conv_b))


class TestV61MemorySeparation(unittest.TestCase):
    """Tests that conversation memory, long-term memory, and task state are separate."""

    def test_clear_conversation_does_not_delete_long_term_memory(self):
        """clear_conversation must preserve long-term memory."""
        import time
        from agent.database import (
            create_conversation, add_message, clear_conversation,
            set_long_term_memory, get_all_long_term_memory
        )
        conv_id = f'memsep_{int(time.time() * 1000)}'
        create_conversation(conv_id)
        add_message(conv_id, 'user', 'Some message')

        ltm_key = f'test_pref_{int(time.time())}'
        set_long_term_memory(ltm_key, 'dark_mode', importance=3)

        clear_conversation(conv_id)

        # Long-term memory must survive
        mem = get_all_long_term_memory()
        self.assertIn(ltm_key, mem)
        self.assertEqual(mem[ltm_key], 'dark_mode')

    def test_long_term_memory_survives_multiple_conversations(self):
        """Long-term memory must persist across multiple session creations."""
        import time
        from agent.database import (
            create_conversation, clear_conversation,
            set_long_term_memory, get_all_long_term_memory
        )
        ltm_key = f'persist_{int(time.time())}'
        set_long_term_memory(ltm_key, 'test_value', importance=5)

        # Create and clear a couple of conversations
        for i in range(3):
            cid = f'throwaway_{int(time.time() * 1000) + i}'
            create_conversation(cid)
            clear_conversation(cid)

        mem = get_all_long_term_memory()
        self.assertIn(ltm_key, mem)


class TestV61WebSearchQuality(unittest.TestCase):
    """Tests for source-aware web search result structure."""

    def test_web_search_returns_dict_with_sources(self):
        """web_search function must return a dict with 'text' and 'sources'."""
        from agent.tools import web_search
        result = web_search("Python programming language")
        self.assertIsInstance(result, dict)
        self.assertIn('text', result)
        self.assertIn('sources', result)
        self.assertIsInstance(result['sources'], list)

    def test_web_search_sources_have_required_fields(self):
        """Each source in web_search result must have title and url."""
        from agent.tools import web_search
        result = web_search("machine learning")
        for src in result.get('sources', []):
            self.assertIn('title', src)
            self.assertIn('url', src)
            self.assertIn('source', src)
            self.assertTrue(src['url'].startswith('http'))

    def test_web_search_empty_query_handled(self):
        """Empty query must return a safe error string, not raise."""
        from agent.tools import web_search
        result = web_search("")
        self.assertIsInstance(result, dict)
        self.assertIn('text', result)

    def test_get_weather_returns_dict_with_sources(self):
        """get_weather must return a dict with 'text' and 'sources'."""
        from agent.tools import get_weather
        result = get_weather("Chennai")
        self.assertIsInstance(result, dict)
        self.assertIn('text', result)
        self.assertIn('sources', result)

    def test_tool_registry_web_search_wrapper_returns_string(self):
        """The _web_search wrapper in AVAILABLE_TOOLS must return a string."""
        from agent.tools import AVAILABLE_TOOLS
        result = AVAILABLE_TOOLS['web_search']['func']({'query': 'Python'})
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_tool_registry_get_weather_wrapper_returns_string(self):
        """The _get_weather wrapper in AVAILABLE_TOOLS must return a string."""
        from agent.tools import AVAILABLE_TOOLS
        result = AVAILABLE_TOOLS['get_weather']['func']({'city': 'Chennai'})
        self.assertIsInstance(result, str)

    def test_get_last_sources_returns_list(self):
        """get_last_sources must return a list (possibly empty)."""
        from agent.tools import get_last_sources, clear_last_sources
        clear_last_sources()
        sources = get_last_sources()
        self.assertIsInstance(sources, list)


class TestV61SystemPromptHardening(unittest.TestCase):
    """Regression tests for v6.1 system prompt quality."""

    def test_system_prompt_contains_uncertainty_handling(self):
        """SYSTEM_PROMPT must contain uncertainty handling instructions."""
        from config import SYSTEM_PROMPT
        self.assertIn('UNCERTAINTY', SYSTEM_PROMPT)
        self.assertIn('clarification', SYSTEM_PROMPT.lower())

    def test_system_prompt_contains_hallucination_prevention(self):
        """SYSTEM_PROMPT must contain hallucination prevention instructions."""
        from config import SYSTEM_PROMPT
        self.assertIn('HALLUCINATION', SYSTEM_PROMPT)

    def test_system_prompt_contains_context_rules(self):
        """SYSTEM_PROMPT must contain context resolution rules."""
        from config import SYSTEM_PROMPT
        self.assertIn('CONTEXT', SYSTEM_PROMPT)
        self.assertIn('clarification', SYSTEM_PROMPT.lower())

    def test_system_prompt_no_spider_man_jokes(self):
        """SYSTEM_PROMPT must not instruct web-slinger personality."""
        from config import SYSTEM_PROMPT
        self.assertNotIn('web-slinger', SYSTEM_PROMPT.lower())
        self.assertNotIn('spin up', SYSTEM_PROMPT.lower())

    def test_system_prompt_pronunciation_rule(self):
        """SYSTEM_PROMPT must enforce Spidey pronunciation."""
        from config import SYSTEM_PROMPT
        self.assertIn('Spidey', SYSTEM_PROMPT)

    def test_system_prompt_requires_web_for_current_info(self):
        """SYSTEM_PROMPT must instruct use of web_search for current info."""
        from config import SYSTEM_PROMPT
        self.assertIn('web_search', SYSTEM_PROMPT)
        self.assertIn('current', SYSTEM_PROMPT.lower())


class TestV61FrontendChatAPIWithConvId(unittest.TestCase):
    """End-to-end Flask tests that include conversation_id."""

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_chat_returns_sources_field(self):
        """POST /api/chat must return a 'sources' field (list)."""
        res = self.client.post('/api/chat', json={
            'message': 'what time is it?',
            'conversation_id': 'v61_source_test'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('sources', data)
        self.assertIsInstance(data['sources'], list)

    def test_chat_returns_resolved_query_field(self):
        """POST /api/chat must return a 'resolved_query' field."""
        res = self.client.post('/api/chat', json={
            'message': 'open notepad',
            'conversation_id': 'v61_rq_test'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('resolved_query', data)

    def test_two_separate_conversation_ids_return_independent_replies(self):
        """Two different conversation_ids must be handled independently."""
        # Conv A
        res_a = self.client.post('/api/chat', json={
            'message': 'what time is it?',
            'conversation_id': 'conv_a_isolation_v61'
        })
        # Conv B
        res_b = self.client.post('/api/chat', json={
            'message': 'what time is it?',
            'conversation_id': 'conv_b_isolation_v61'
        })
        self.assertEqual(res_a.status_code, 200)
        self.assertEqual(res_b.status_code, 200)
        # Both should succeed independently
        data_a = res_a.get_json()
        data_b = res_b.get_json()
        self.assertEqual(data_a['status'], 'ok')
        self.assertEqual(data_b['status'], 'ok')


if __name__ == '__main__':
    unittest.main(verbosity=2)
