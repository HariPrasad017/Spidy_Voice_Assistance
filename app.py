"""
S.P.I.D.Y (Spider-Man Personal Intelligence Digital Yield-system)
Main Flask Application Server
"""

import os
import sys
import time
import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
import threading
import platform
import subprocess
import requests
import re

# Reconfigure stdout/stderr for Windows console compatibility
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from flask import Flask, request, jsonify

# Import configuration and portable environment
from config import (
    BASE_DIR,
    NOTES_FILE,
    REMINDERS_FILE,
    GROQ_API_KEY,
    GROQ_MODEL,
    SYSTEM_PROMPT,
    FFMPEG_AVAILABLE,
    FFMPEG_PATH,
    TORCH_DEVICE,
    GPU_NAME,
    logger,
    groq_circuit_breaker
)

# Import deterministic commands and normalization
from commands import (
    parse_command,
    normalize_voice_text,
    open_app,
    take_screenshot,
    load_json,
    save_json
)

# Import new V6 Agent modules
from agent.router import route_conversation
from agent.database import (
    create_conversation, get_all_long_term_memory, clear_conversation,
    get_task_state, add_message, get_recent_messages,
    get_pending_clarification, set_pending_clarification, clear_pending_clarification
)
from agent.task_engine import (
    is_multi_step_request, create_task_plan, execute_task,
    resume_task, cancel_task
)
from agent.tools import AVAILABLE_TOOLS

# Import AI modules
try:
    from whisper_asr import whisper_asr
    WHISPER_AVAILABLE = True
except Exception as e:
    logger.error(f"Whisper ASR import failed: {e}")
    whisper_asr = None
    WHISPER_AVAILABLE = False

try:
    from intent_detector import intent_detector
    INTENT_AVAILABLE = True
except Exception as e:
    logger.error(f"Intent detector import failed: {e}")
    intent_detector = None
    INTENT_AVAILABLE = False

try:
    from sentiment_analyzer import sentiment_analyzer
    SENTIMENT_AVAILABLE = True
except Exception as e:
    logger.error(f"Sentiment analyzer import failed: {e}")
    sentiment_analyzer = None
    SENTIMENT_AVAILABLE = False

# Initialize Groq client
groq_client = None
if GROQ_API_KEY:
    try:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)
        logger.info("Groq client initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {e}")
else:
    logger.warning("GROQ_API_KEY is not set in environment or .env. Conversational fallback will be disabled.")

# Flask app
app = Flask(__name__, static_folder='static', static_url_path='')
app.config['JSON_AS_ASCII'] = False  # Don't escape Unicode/emoji in JSON responses
app.config['JSONIFY_MIMETYPE'] = 'application/json; charset=utf-8'

# ===== REMINDER BACKGROUND WORKER =====
def background_reminder_worker():
    while True:
        try:
            now = datetime.datetime.now(IST)
            reminders = load_json(REMINDERS_FILE)
            updated = False
            for r in reminders:
                if not r.get('fired') and r.get('time'):
                    try:
                        rt = datetime.datetime.strptime(r['time'], '%Y-%m-%d %H:%M')
                        if now >= rt:
                            r['fired'] = True
                            updated = True
                            logger.info(f"Triggering reminder: {r.get('text')}")
                            if platform.system() == "Windows":
                                # Safe Windows popup notification
                                msg_text = r.get("text", "Reminder!").replace('"', '')
                                subprocess.Popen(['msg', '*', f'S.P.I.D.Y REMINDER: {msg_text}'], shell=False)
                    except Exception as parse_e:
                        logger.warning(f"Reminder parse error: {parse_e}")
            if updated:
                save_json(REMINDERS_FILE, reminders)
        except Exception as e:
            logger.error(f"Error in reminder worker: {e}")
        time.sleep(30)

threading.Thread(target=background_reminder_worker, daemon=True).start()

# ===== ROUTES =====
@app.route('/')
def index():
    html_path = os.path.join(BASE_DIR, 'static', 'SPIDY.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    from flask import Response
    return Response(content, content_type='text/html; charset=utf-8')

# ===== HELPER FUNCTIONS FOR CONTEXT & CLARIFICATION =====

def is_explicit_safety_command(text: str) -> bool:
    """Return True if text contains an explicit OS power/lock command that must execute immediately."""
    t = text.lower().strip()
    if any(p in t for p in ['shut down', 'shutdown', 'restart', 'reboot', 'cancel shutdown']):
        return True
    if 'sleep' in t and any(x in t for x in ['computer', 'laptop', 'system', 'pc']):
        return True
    # Never treat product queries as lock commands
    if any(b in t for b in ['lenovo', 'loq', 'asus', 'dell', 'hp', 'acer', 'macbook', 'legion']):
        return False
    lock_patterns = [
        r'^(?:please\s+)?lock\s+(?:the\s+|my\s+|this\s+)?(?:computer|workstation|pc|screen)[.?!]*$',
        r'^lock\s+down\s+(?:the\s+|my\s+)?(?:computer|pc|workstation)[.?!]*$',
        r'^lock\s+(?:workstation|pc|screen|computer)[.?!]*$'
    ]
    return any(re.search(p, t) for p in lock_patterns)


def is_previous_conversation_query(text: str) -> bool:
    """Detect queries asking for previous conversation response or previous request."""
    t = text.lower().strip()
    t = re.sub(r'^(?:hello|hi|hey|spidey|please)[,\s]+', '', t).strip()
    triggers = [
        "give me the response for the previous conversation",
        "give me the response of the previous conversation",
        "give me the response for the previous request",
        "give me the response to the previous conversation",
        "give me the response to the previous request",
        "response for the previous conversation",
        "response to the previous conversation",
        "what was the response to my previous question",
        "what was the answer to my previous question",
        "answer my previous question",
        "repeat the previous response",
        "what was your previous response",
        "what was the previous response",
        "what did you say previously",
        "response for previous conversation",
        "previous conversation response"
    ]
    if any(tr in t for tr in triggers):
        return True
    if "previous conversation" in t and any(w in t for w in ["response", "answer", "what was", "give me"]):
        return True
    if "previous request" in t and any(w in t for w in ["response", "answer", "what was", "give me"]):
        return True
    return False


def handle_previous_conversation_request(conv_id: str, user_msg: str) -> dict:
    """
    Safely resolves queries asking about previous conversation or requests.
    Never sends to web search.
    """
    history = get_recent_messages(conv_id, limit=20)
    user_queries = [m["content"] for m in history if m["role"] == "user" and m["content"] != user_msg]
    assistant_replies = [m["content"] for m in history if m["role"] == "assistant"]

    if not user_queries:
        reply = "There are no previous requests in this conversation yet. How can I help you?"
        add_message(conv_id, "user", user_msg)
        add_message(conv_id, "assistant", reply)
        return {
            'status': 'ok',
            'reply': reply,
            'sources': [],
            'resolved_query': user_msg,
            'route': 'previous_conversation_resolution'
        }

    # If there is exactly one previous user query, resolve/repeat it
    if len(user_queries) == 1:
        last_req = user_queries[0]
        if assistant_replies:
            last_resp = assistant_replies[-1]
            reply = f"For your previous request ('{last_req}'), the response was:\n\n{last_resp}"
        else:
            reply = f"Your previous request was '{last_req}'. Let me address that for you."
        add_message(conv_id, "user", user_msg)
        add_message(conv_id, "assistant", reply)
        return {
            'status': 'ok',
            'reply': reply,
            'sources': [],
            'resolved_query': last_req,
            'route': 'previous_conversation_resolution'
        }

    # Multiple distinct previous user queries -> ask concise clarification
    reply = "Sure — which previous request do you want me to answer?"
    set_pending_clarification(conv_id, {
        "type": "previous_request_disambiguation",
        "prompt": reply,
        "candidate": None,
        "user_queries": user_queries[-5:],
        "conversation_id": conv_id
    })
    add_message(conv_id, "user", user_msg)
    add_message(conv_id, "assistant", reply)
    return {
        'status': 'ok',
        'reply': reply,
        'sources': [],
        'resolved_query': user_msg,
        'route': 'previous_conversation_disambiguation'
    }


def handle_pending_clarification(conv_id: str, user_msg: str, normalized_msg: str, pending: dict):
    """
    Evaluates user response against an active pending clarification.
    Returns a dict response if handled, or None if user switched subjects.
    """
    clean_low = normalized_msg.lower().strip()
    clar_type = pending.get("type", "entity_confirmation")
    candidate = pending.get("candidate", "")

    affirmatives = {
        'yes', 'yeah', 'yep', 'yup', 'sure', 'ok', 'okay',
        'correct', "that's correct", "that is correct",
        "that's right", "that is right", "exactly",
        "yes that's it", "yes that is it", "yes that's right",
        "yes please", "confirm", "confirmed", "proceed",
        "go ahead", "right", "absolutely", "definitely",
        "true", "that's it", "indeed"
    }

    negatives = {
        'no', 'nope', 'nah', 'not that', 'incorrect', 'wrong',
        "that's wrong", "that's not it", "neither", "none",
        "cancel", "stop", "abort"
    }

    # Check for affirmation
    is_affirmative = (
        clean_low in affirmatives or
        any(clean_low.startswith(a + " ") or clean_low.startswith(a + ",") for a in affirmatives)
    )
    if candidate and candidate.lower() in clean_low:
        is_affirmative = True

    # Check for negative
    is_negative = (
        clean_low in negatives or
        any(clean_low.startswith(n + " ") or clean_low.startswith(n + ",") for n in negatives)
    )

    if clar_type == "entity_confirmation":
        if is_affirmative:
            clear_pending_clarification(conv_id)
            reply = f"Yes — you mean the {candidate}. What would you like to know about it?"
            add_message(conv_id, "user", user_msg)
            add_message(conv_id, "assistant", reply)
            return {
                'status': 'ok',
                'reply': reply,
                'resolved_query': candidate,
                'sources': [],
                'route': 'clarification_confirmed'
            }
        elif is_negative:
            clear_pending_clarification(conv_id)
            reply = "Understood. What were you referring to, or how can I help you?"
            add_message(conv_id, "user", user_msg)
            add_message(conv_id, "assistant", reply)
            return {
                'status': 'ok',
                'reply': reply,
                'resolved_query': user_msg,
                'sources': [],
                'route': 'clarification_rejected'
            }
        else:
            # User changed subject entirely — clear pending clarification and continue
            clear_pending_clarification(conv_id)
            return None

    elif clar_type == "previous_request_disambiguation":
        if is_negative:
            clear_pending_clarification(conv_id)
            reply = "Understood. How can I help you today?"
            add_message(conv_id, "user", user_msg)
            add_message(conv_id, "assistant", reply)
            return {
                'status': 'ok',
                'reply': reply,
                'resolved_query': user_msg,
                'sources': [],
                'route': 'clarification_rejected'
            }
        else:
            user_queries = pending.get("user_queries", [])
            matched_query = None
            for q in reversed(user_queries):
                q_words = set(re.findall(r'\w+', q.lower()))
                c_words = set(re.findall(r'\w+', clean_low))
                if q_words & c_words - {'the', 'about', 'a', 'an', 'what', 'is', 'me', 'tell', 'yes', 'that'}:
                    matched_query = q
                    break
            clear_pending_clarification(conv_id)
            if matched_query:
                reply = f"Regarding '{matched_query}': let me help you with that."
                add_message(conv_id, "user", user_msg)
                add_message(conv_id, "assistant", reply)
                return {
                    'status': 'ok',
                    'reply': reply,
                    'resolved_query': matched_query,
                    'sources': [],
                    'route': 'previous_conversation_resolution'
                }
            return None

    clear_pending_clarification(conv_id)
    return None


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Core Chat Endpoint.
    Architecture:
      Priority 1: Explicit safety-critical command
      Priority 2: Active confirmation / pending clarification
      Priority 3: Active task continuation
      Priority 4: Explicitly referenced previous conversation request
      Priority 5: Multi-Step Task Execution Engine
      Priority 6: Deterministic Command Parsing
      Priority 7: HuggingFace Zero-Shot Intent Detection
      Priority 8: Sentiment Analysis (Tone adjustment)
      Priority 9: Groq Conversational AI Agent Loop
    """
    try:
        data = request.get_json(silent=True) or {}
        user_msg = data.get('message', '').strip()
        conv_id = data.get('conversation_id', 'default_session')
        
        # Ensure conversation exists
        create_conversation(conv_id, title="Main Session")

        if not user_msg:
            return jsonify({
                'status': 'error',
                'reply': 'I did not catch that! Please try speaking or typing again.',
                'message': 'Empty message received.'
            }), 400

        normalized_msg = normalize_voice_text(user_msg)
        clean_low = normalized_msg.lower().strip()

        # ----------------------------------------------------
        # Priority 1: Explicit Safety-Critical Command
        # ----------------------------------------------------
        if is_explicit_safety_command(normalized_msg):
            cmd_res = parse_command(normalized_msg)
            if cmd_res:
                rep_text = cmd_res.get('message', '') if isinstance(cmd_res, dict) else str(cmd_res)
                add_message(conv_id, "user", user_msg)
                add_message(conv_id, "assistant", rep_text)
                return jsonify({
                    'status': 'ok',
                    'reply': rep_text,
                    'sources': [],
                    'resolved_query': user_msg,
                    'route': 'safety_critical_command'
                })

        # ----------------------------------------------------
        # Priority 2: Active Confirmation / Pending Clarification
        # ----------------------------------------------------
        # Check active pending clarification first
        pending = get_pending_clarification(conv_id)
        if pending and isinstance(pending, dict):
            clar_res = handle_pending_clarification(conv_id, user_msg, normalized_msg, pending)
            if clar_res:
                return jsonify(clar_res)

        # Check multi-step task WAITING_CONFIRMATION
        active_task = get_task_state(conv_id)
        if active_task and isinstance(active_task, dict) and "steps" in active_task:
            task_status = active_task.get("status")
            if task_status == "WAITING_CONFIRMATION" and any(clean_low.startswith(w) for w in ["yes", "confirm", "proceed", "continue", "no", "cancel", "stop", "abort", "sure", "ok"]):
                exec_res = resume_task(conv_id, clean_low)
                add_message(conv_id, "user", user_msg)
                add_message(conv_id, "assistant", exec_res.get("reply", ""))
                return jsonify({
                    'status': 'ok',
                    'reply': exec_res.get('reply'),
                    'task_status': exec_res.get('status'),
                    'sources': exec_res.get('sources', []),
                    'resolved_query': user_msg,
                    'route': 'task_engine_confirmation'
                })

        # ----------------------------------------------------
        # Priority 3: Active Task Continuation
        # ----------------------------------------------------
        if active_task and isinstance(active_task, dict) and "steps" in active_task:
            # Cancel task
            if clean_low in ["cancel task", "cancel that task", "stop task", "abort task"]:
                cancel_res = cancel_task(conv_id)
                add_message(conv_id, "user", user_msg)
                add_message(conv_id, "assistant", cancel_res.get("reply", ""))
                return jsonify({
                    'status': 'ok',
                    'reply': cancel_res.get('reply'),
                    'task_status': 'CANCELLED',
                    'sources': [],
                    'resolved_query': user_msg,
                    'route': 'task_engine_cancel'
                })

            # Restart / Retry task
            if clean_low in ["start that task again", "run that task again", "restart task", "retry task", "start the task again"]:
                resume_res = resume_task(conv_id, "again")
                add_message(conv_id, "user", user_msg)
                add_message(conv_id, "assistant", resume_res.get("reply", ""))
                return jsonify({
                    'status': 'ok',
                    'reply': resume_res.get('reply'),
                    'task_status': resume_res.get('status'),
                    'sources': resume_res.get('sources', []),
                    'resolved_query': user_msg,
                    'route': 'task_engine_retry'
                })

        # Reference continuation: "Save that to my notes"
        if any(p in clean_low for p in ['save that to', 'save this to', 'add that to', 'add this to']) and ('note' in clean_low or 'notes' in clean_low):
            target_text = ""
            if active_task and isinstance(active_task, dict) and "steps" in active_task:
                for s in reversed(active_task.get("steps", [])):
                    if s.get("status") == "COMPLETED" and s.get("result"):
                        target_text = s.get("result")
                        break
            if not target_text:
                history = get_recent_messages(conv_id, limit=4)
                for h in reversed(history):
                    if h.get("role") == "assistant" and h.get("content"):
                        target_text = h.get("content")
                        break

            if target_text:
                save_func = AVAILABLE_TOOLS.get("save_note", {}).get("func")
                if save_func:
                    save_res = save_func({"text": target_text})
                    reply_text = f"Saved to your notes: '{target_text[:70]}...'"
                    add_message(conv_id, "user", user_msg)
                    add_message(conv_id, "assistant", reply_text)
                    return jsonify({
                        'status': 'ok',
                        'reply': reply_text,
                        'sources': [],
                        'resolved_query': user_msg,
                        'route': 'context_continuation'
                    })

        # ----------------------------------------------------
        # Priority 4: Explicitly Referenced Previous Conversation Request
        # ----------------------------------------------------
        if is_previous_conversation_query(normalized_msg):
            prev_res = handle_previous_conversation_request(conv_id, user_msg)
            return jsonify(prev_res)

        # ----------------------------------------------------
        # Priority 5: Multi-Step Request Detection & Execution
        # ----------------------------------------------------
        if is_multi_step_request(normalized_msg):
            plan = create_task_plan(normalized_msg, conv_id, groq_client)
            exec_res = execute_task(plan, conv_id)
            add_message(conv_id, "user", user_msg)
            add_message(conv_id, "assistant", exec_res.get("reply", ""))
            return jsonify({
                'status': 'ok',
                'reply': exec_res.get('reply'),
                'task_status': exec_res.get('status'),
                'sources': exec_res.get('sources', []),
                'resolved_query': user_msg,
                'route': 'task_engine'
            })

        # ----------------------------------------------------
        # Priority 6: Deterministic Command Parsing
        # ----------------------------------------------------
        command_result = parse_command(normalized_msg)
        if command_result:
            rep_text = command_result.get('message', '') if isinstance(command_result, dict) else str(command_result)
            add_message(conv_id, "user", user_msg)
            add_message(conv_id, "assistant", rep_text)

            # Auto-detect if command result asked a clarification
            if isinstance(command_result, str) and ("did you mean" in command_result.lower() or "do you mean" in command_result.lower()):
                cand = "Lenovo LOQ laptop" if ("lenovo" in command_result.lower() and "loq" in command_result.lower()) else None
                if not cand:
                    m = re.search(r'(?:did you mean|do you mean)\s+(?:the\s+)?([^?.,]+)', command_result, re.IGNORECASE)
                    if m:
                        cand = m.group(1).strip()
                if cand:
                    set_pending_clarification(conv_id, {
                        "type": "entity_confirmation",
                        "candidate": cand,
                        "prompt": command_result,
                        "expected_yes_action": "resolve_to_candidate",
                        "expected_no_action": "request_alternative",
                        "conversation_id": conv_id
                    })

            if isinstance(command_result, dict):
                return jsonify({
                    'status': 'ok',
                    'reply': rep_text,
                    'action': command_result.get('action'),
                    'url': command_result.get('url'),
                    'sources': [],
                    'resolved_query': user_msg,
                    'route': 'deterministic_action'
                })
            return jsonify({
                'status': 'ok',
                'reply': command_result,
                'sources': [],
                'resolved_query': user_msg,
                'route': 'deterministic_command'
            })

        # ----------------------------------------------------
        # Priority 7: HuggingFace Zero-Shot Intent Detection
        # ----------------------------------------------------
        intent_info = None
        if INTENT_AVAILABLE and intent_detector and intent_detector.loaded:
            try:
                intent_info = intent_detector.detect(normalized_msg)
                if intent_info and intent_info.get('confidence', 0) >= 0.65:
                    action = intent_info['action']
                    conf = intent_info['confidence']
                    intent_lbl = intent_info['intent']

                    if action == 'open_app':
                        app_target = normalized_msg.replace('open', '').replace('launch', '').strip()
                        reply = open_app(app_target)
                        add_message(conv_id, "user", user_msg)
                        add_message(conv_id, "assistant", reply)
                        return jsonify({'status': 'ok', 'reply': reply, 'intent': intent_lbl, 'confidence': conf, 'sources': [], 'resolved_query': user_msg, 'route': 'intent_execution'})

                    elif action == 'screenshot':
                        reply = take_screenshot()
                        add_message(conv_id, "user", user_msg)
                        add_message(conv_id, "assistant", reply)
                        return jsonify({'status': 'ok', 'reply': reply, 'intent': intent_lbl, 'confidence': conf, 'sources': [], 'resolved_query': user_msg, 'route': 'intent_execution'})

                    elif action == 'datetime':
                        now = datetime.datetime.now(IST)
                        reply = f"It's {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d, %Y')}."
                        add_message(conv_id, "user", user_msg)
                        add_message(conv_id, "assistant", reply)
                        return jsonify({'status': 'ok', 'reply': reply, 'intent': intent_lbl, 'confidence': conf, 'sources': [], 'resolved_query': user_msg, 'route': 'intent_execution'})

                    elif action == 'greet':
                        hour = datetime.datetime.now(IST).hour
                        g = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
                        reply = f"{g}! I'm Spidey, your personal AI assistant. How may I assist you?"
                        add_message(conv_id, "user", user_msg)
                        add_message(conv_id, "assistant", reply)
                        return jsonify({'status': 'ok', 'reply': reply, 'intent': intent_lbl, 'confidence': conf, 'sources': [], 'resolved_query': user_msg, 'route': 'intent_execution'})

                    elif action == 'news':
                        rep_news = "Opening the latest top headlines for you!"
                        add_message(conv_id, "user", user_msg)
                        add_message(conv_id, "assistant", rep_news)
                        return jsonify({
                            'status': 'ok',
                            'reply': rep_news,
                            'action': 'open_url',
                            'url': 'https://news.google.com/',
                            'intent': intent_lbl,
                            'sources': [],
                            'resolved_query': user_msg,
                            'route': 'intent_action'
                        })
            except Exception as e:
                logger.warning(f"Intent detector routing non-fatal error: {e}")

        # ----------------------------------------------------
        # Priority 8: Sentiment Analysis for Tone Adaptation
        # ----------------------------------------------------
        sentiment_label = 'NEUTRAL'
        tone_instruction = ''
        if SENTIMENT_AVAILABLE and sentiment_analyzer and sentiment_analyzer.loaded:
            try:
                s_res = sentiment_analyzer.analyze(user_msg)
                sentiment_label = s_res.get('label', 'NEUTRAL')
                tone_instruction = f" ({s_res.get('tone', '')})" if s_res.get('tone') != 'normal' else ''
            except Exception as e:
                logger.warning(f"Sentiment analysis non-fatal error: {e}")

        # ----------------------------------------------------
        # Priority 9: Groq Conversational AI Agent (V6.1)
        # ----------------------------------------------------
        agent_result = route_conversation(user_msg, conv_id, groq_client)
        agent_reply = agent_result.get('reply', '')

        # Auto-detect if agent asked a clarification
        if isinstance(agent_reply, str) and ("did you mean" in agent_reply.lower() or "do you mean" in agent_reply.lower()):
            m = re.search(r'(?:did you mean|do you mean)\s+(?:the\s+)?([^?.,]+)', agent_reply, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                set_pending_clarification(conv_id, {
                    "type": "entity_confirmation",
                    "candidate": cand,
                    "prompt": agent_reply,
                    "expected_yes_action": "resolve_to_candidate",
                    "expected_no_action": "request_alternative",
                    "conversation_id": conv_id
                })

        return jsonify({
            'status': 'ok',
            'reply': agent_reply,
            'action': agent_result.get('action'),
            'sources': agent_result.get('sources', []),
            'resolved_query': agent_result.get('resolved_query', user_msg),
            'sentiment': sentiment_label,
            'intent': intent_info['intent'] if intent_info else 'conversational',
            'route': 'agent_ai'
        })

    except Exception as e:
        logger.error(f"Unhandled error in /api/chat: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'reply': "An unexpected error occurred while processing your request.",
            'message': str(e)[:100]
        }), 500

# ===== WHISPER ASR ENDPOINTS =====
@app.route('/api/whisper/transcribe', methods=['POST'])
def whisper_transcribe():
    """
    Receives audio recording blob from browser, transcribes via Whisper,
    and returns standardized JSON.
    """
    try:
        if not WHISPER_AVAILABLE or not whisper_asr:
            return jsonify({'status': 'error', 'message': 'Whisper ASR is not available.', 'text': ''}), 503

        if not whisper_asr.loaded:
            return jsonify({'status': 'loading', 'message': 'Whisper model is loading.', 'text': ''}), 503

        if 'audio' not in request.files:
            return jsonify({'status': 'error', 'message': 'No audio file provided.', 'text': ''}), 400

        audio_file = request.files['audio']
        audio_bytes = audio_file.read()

        if not audio_bytes:
            return jsonify({'status': 'error', 'message': 'Uploaded audio is empty.', 'text': ''}), 400

        language = request.form.get('language', 'auto')
        text, detected_lang = whisper_asr.transcribe_from_bytes(audio_bytes, language=language)

        if text:
            return jsonify({
                'status': 'ok',
                'text': text,
                'language': detected_lang,
                'model': whisper_asr.model_size
            })
        else:
            return jsonify({
                'status': 'no_speech',
                'text': '',
                'message': detected_lang or 'No speech detected.'
            })

    except Exception as e:
        logger.error(f"Error in /api/whisper/transcribe: {e}")
        return jsonify({'status': 'error', 'message': str(e), 'text': ''}), 500

@app.route('/api/whisper/record', methods=['POST'])
def whisper_record():
    """
    Records from desktop microphone for specified duration.
    """
    try:
        if not WHISPER_AVAILABLE or not whisper_asr or not whisper_asr.loaded:
            return jsonify({'status': 'error', 'message': 'Whisper ASR is not ready.', 'text': ''}), 503

        data = request.get_json(silent=True) or {}
        duration = int(data.get('duration', 5))
        language = data.get('language', 'auto')

        text, lang = whisper_asr.record_audio(duration=duration, language=language)
        if text:
            return jsonify({'status': 'ok', 'text': text, 'language': lang})
        return jsonify({'status': 'no_speech', 'text': '', 'message': lang})

    except Exception as e:
        logger.error(f"Error in /api/whisper/record: {e}")
        return jsonify({'status': 'error', 'message': str(e), 'text': ''}), 500

@app.route('/api/whisper/status', methods=['GET'])
def whisper_status():
    status_info = whisper_asr.get_status() if WHISPER_AVAILABLE and whisper_asr else 'unavailable'
    return jsonify({'status': 'ok', 'whisper': status_info})

# ===== NOTES & REMINDERS ENDPOINTS =====
@app.route('/api/notes', methods=['GET', 'POST', 'DELETE'])
def notes_api():
    if request.method == 'GET':
        return jsonify({'status': 'ok', 'notes': load_json(NOTES_FILE)})
    elif request.method == 'POST':
        data = request.get_json(silent=True) or {}
        text = data.get('text', '').strip()
        if not text:
            return jsonify({'status': 'error', 'message': 'Note text cannot be empty'}), 400
        notes = load_json(NOTES_FILE)
        notes.append({'text': text, 'time': datetime.datetime.now(IST).isoformat()})
        save_json(NOTES_FILE, notes)
        return jsonify({'status': 'ok', 'message': 'Note saved', 'notes': notes})
    elif request.method == 'DELETE':
        save_json(NOTES_FILE, [])
        return jsonify({'status': 'ok', 'message': 'All notes cleared'})

@app.route('/api/reminders', methods=['GET', 'POST'])
def reminders_api():
    if request.method == 'GET':
        rems = load_json(REMINDERS_FILE)
        active = [r for r in rems if not r.get('fired')]
        return jsonify({'status': 'ok', 'reminders': active})
    elif request.method == 'POST':
        data = request.get_json(silent=True) or {}
        text = data.get('text', 'Reminder').strip()
        rem_time = data.get('time', '').strip()
        if not rem_time:
            return jsonify({'status': 'error', 'message': 'Reminder time required'}), 400
        rems = load_json(REMINDERS_FILE)
        rems.append({'text': text, 'time': rem_time, 'fired': False})
        save_json(REMINDERS_FILE, rems)
        return jsonify({'status': 'ok', 'message': 'Reminder scheduled', 'reminders': rems})

# ===== STATUS & HEALTH ENDPOINT =====
@app.route('/api/status', methods=['GET'])
def status():
    """
    Comprehensive system health check and status reporting.
    """
    try:
        import torch
        cuda_avail = torch.cuda.is_available()
    except Exception:
        cuda_avail = False

    whisper_stat = whisper_asr.get_status() if WHISPER_AVAILABLE and whisper_asr else 'unavailable'
    whisper_sz = whisper_asr.model_size if WHISPER_AVAILABLE and whisper_asr else 'none'
    intent_stat = intent_detector.get_status() if INTENT_AVAILABLE and intent_detector else 'unavailable'
    sentiment_stat = sentiment_analyzer.get_status() if SENTIMENT_AVAILABLE and sentiment_analyzer else 'unavailable'

    groq_stat = 'ready' if groq_client else ('missing_key' if not GROQ_API_KEY else 'error')

    _cb_open = groq_circuit_breaker.is_open
    _cb_remaining = max(0, int(groq_circuit_breaker.cooldown_until - time.time())) if _cb_open else 0

    return jsonify({
        'status': 'online',
        'application': 'S.P.I.D.Y AI Voice Assistant',
        'version': '6.2.1',
        'groq': {
            'status': groq_stat,
            'model': GROQ_MODEL,
            'circuit': {
                'open': _cb_open,
                'cooldown_remaining_seconds': _cb_remaining
            }
        },
        'whisper': {
            'status': whisper_stat,
            'model': whisper_sz
        },
        'intent_detector': intent_stat,
        'sentiment_analyzer': sentiment_stat,
        'cuda': {
            'available': cuda_avail,
            'gpu_name': GPU_NAME
        },
        'ffmpeg': {
            'available': FFMPEG_AVAILABLE,
            'path': FFMPEG_PATH or 'Not in PATH'
        },
        'platform': platform.system(),
        'python_version': platform.python_version()
    })

# ===== SENTIMENT ENDPOINTS =====
@app.route('/api/sentiment', methods=['POST'])
def analyze_sentiment_endpoint():
    try:
        data = request.get_json(silent=True) or {}
        text = data.get('text', '')
        if SENTIMENT_AVAILABLE and sentiment_analyzer:
            res = sentiment_analyzer.analyze(text)
            return jsonify({'status': 'ok', **res})
        return jsonify({'status': 'error', 'label': 'NEUTRAL', 'message': 'Sentiment model not loaded.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/sentiment/batch', methods=['POST'])
def batch_sentiment_endpoint():
    try:
        data = request.get_json(silent=True) or {}
        texts = data.get('texts', [])
        if SENTIMENT_AVAILABLE and sentiment_analyzer:
            results = sentiment_analyzer.batch_analyze(texts)
            return jsonify({'status': 'ok', 'results': results, 'count': len(results)})
        return jsonify({'status': 'error', 'message': 'Sentiment model not loaded.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ===== NEWS & WEATHER APIS =====
@app.route('/api/news', methods=['GET'])
def get_news():
    try:
        category = request.args.get('category', 'technology')
        # RSS feed fallback for 100% free reliability
        import xml.etree.ElementTree as ET
        feeds = {
            'technology': 'https://feeds.feedburner.com/TechCrunch',
            'general': 'https://timesofindia.indiatimes.com/rssfeedstopstories.cms',
            'sports': 'https://www.espncricinfo.com/rss/content/story/feeds/0.xml',
        }
        feed_url = feeds.get(category, feeds['general'])
        r = requests.get(feed_url, timeout=5)
        root = ET.fromstring(r.content)
        items = root.findall('.//item')[:5]
        news = [
            {
                'title': i.find('title').text if i.find('title') is not None else '',
                'description': i.find('description').text if i.find('description') is not None else ''
            }
            for i in items
        ]
        return jsonify({'status': 'ok', 'articles': news, 'source': 'RSS'})
    except Exception as e:
        logger.warning(f"News fetch error: {e}")
        return jsonify({'status': 'error', 'message': str(e), 'articles': []})

@app.route('/api/weather', methods=['GET'])
def get_weather():
    city = request.args.get('city', 'Chennai')
    try:
        r = requests.get(f'https://wttr.in/{city}?format=j1', timeout=5)
        data = r.json()
        current = data['current_condition'][0]
        return jsonify({
            'status': 'ok',
            'city': city,
            'temp': current['temp_C'],
            'description': current['weatherDesc'][0]['value'],
            'humidity': current['humidity'],
            'source': 'wttr.in'
        })
    except Exception as e:
        logger.warning(f"Weather fetch error: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

# ===== V6 SESSION & MEMORY ENDPOINTS =====
@app.route('/api/conversations', methods=['POST'])
def new_conversation():
    data = request.get_json(silent=True) or {}
    conv_id = data.get('conversation_id', f"sess_{int(time.time())}")
    create_conversation(conv_id, "New Session")
    return jsonify({'status': 'ok', 'conversation_id': conv_id})

@app.route('/api/conversations/<conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    clear_conversation(conv_id)
    return jsonify({'status': 'ok', 'message': 'Conversation cleared'})

@app.route('/api/memory', methods=['GET'])
def get_memory():
    mem = get_all_long_term_memory()
    return jsonify({'status': 'ok', 'memory': mem})

# ===== STARTUP SUMMARY =====
def print_startup_banner():
    cuda_str = f"AVAILABLE ({GPU_NAME})" if TORCH_DEVICE and TORCH_DEVICE.type == 'cuda' else "CPU ONLY"
    ffmpeg_str = f"READY ({FFMPEG_PATH})" if FFMPEG_AVAILABLE else "NOT FOUND"
    whisper_str = whisper_asr.get_status() if WHISPER_AVAILABLE and whisper_asr else "FAILED"
    intent_str = intent_detector.get_status() if INTENT_AVAILABLE and intent_detector else "FAILED"
    sent_str = sentiment_analyzer.get_status() if SENTIMENT_AVAILABLE and sentiment_analyzer else "FAILED"
    groq_str = f"READY ({GROQ_MODEL})" if groq_client else "DISABLED (No API key)"

    banner = f"""
==================================================
SPIDY Voice Assistant - System Startup
==================================================
Groq AI:          {groq_str}
Whisper ASR:      {whisper_str}
Intent Detector:  {intent_str}
Sentiment:        {sent_str}
CUDA / GPU:       {cuda_str}
FFmpeg:           {ffmpeg_str}
Flask Server:     READY on port {os.environ.get('PORT', 5000)}
==================================================
"""
    try:
        print(banner, flush=True)
    except Exception:
        pass

if __name__ == '__main__':
    print_startup_banner()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)