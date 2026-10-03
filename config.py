"""
S.P.I.D.Y Configuration & Portable Environment Setup
"""

import os
import time
import re
import shutil
import platform
import logging
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent
NOTES_FILE = str(BASE_DIR / 'spidy_notes.json')
REMINDERS_FILE = str(BASE_DIR / 'spidy_reminders.json')

# Load .env
load_dotenv(dotenv_path=BASE_DIR / '.env')

# Logging configuration
LOG_LEVEL = logging.DEBUG if os.getenv('SPIDY_DEBUG', 'false').lower() == 'true' else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format='[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("SPIDY")

# Groq Configuration
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
GROQ_MODEL = os.getenv('GROQ_MODEL', 'openai/gpt-oss-20b')

# Whisper Configuration
WHISPER_MODEL_SIZE = os.getenv('WHISPER_MODEL_SIZE', 'base')
WHISPER_LANGUAGE = os.getenv('WHISPER_LANGUAGE', 'auto')

# Weather & News Keys (Optional)
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY', '')
NEWS_API_KEY = os.getenv('NEWS_API_KEY', '')

# Portable FFmpeg Discovery
def setup_ffmpeg():
    """
    Ensure ffmpeg and ffprobe are in PATH.
    Searches system PATH and standard Windows fallback paths.
    """
    ffmpeg_exe = shutil.which("ffmpeg")
    if ffmpeg_exe:
        return ffmpeg_exe

    # Common Windows installation directories
    candidate_dirs = [
        r"E:\ffmpeg-9.0.2-essentials_build\bin",
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
        r"C:\ProgramData\chocolatey\bin",
        str(BASE_DIR / "ffmpeg" / "bin")
    ]

    for c_dir in candidate_dirs:
        candidate_file = os.path.join(c_dir, "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
        if os.path.isfile(candidate_file):
            os.environ["PATH"] = c_dir + os.pathsep + os.environ.get("PATH", "")
            logger.info(f"Discovered and added FFmpeg to PATH: {c_dir}")
            return candidate_file

    return None

FFMPEG_PATH = setup_ffmpeg()
FFMPEG_AVAILABLE = bool(FFMPEG_PATH and shutil.which("ffmpeg"))


# Device Selection (CUDA -> CPU)
def get_torch_device():
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            return torch.device('cuda'), gpu_name
        return torch.device('cpu'), "CPU"
    except Exception:
        return None, "Unavailable"

TORCH_DEVICE, GPU_NAME = get_torch_device()

# Safe Application Whitelist and Aliases
APPLICATION_WHITELIST = {
    'notepad': {
        'windows_cmd': ['notepad.exe'],
        'display_name': 'Notepad',
        'aliases': ['notepad', 'noted', 'note pad', 'not bad', 'not that', 'notespad']
    },
    'calculator': {
        'windows_cmd': ['calc.exe'],
        'display_name': 'Calculator',
        'aliases': ['calculator', 'calc', 'calculate', 'calculates']
    },
    'chrome': {
        'windows_cmd': ['cmd.exe', '/c', 'start', 'chrome'],
        'display_name': 'Google Chrome',
        'aliases': ['chrome', 'google chrome', 'browser', 'web browser']
    },
    'edge': {
        'windows_cmd': ['cmd.exe', '/c', 'start', 'msedge'],
        'display_name': 'Microsoft Edge',
        'aliases': ['edge', 'msedge', 'microsoft edge']
    },
    'vscode': {
        'windows_cmd': ['cmd.exe', '/c', 'code', '.'],
        'display_name': 'Visual Studio Code',
        'aliases': ['vs code', 'vscode', 'visual studio code', 'code']
    },
    'explorer': {
        'windows_cmd': ['explorer.exe'],
        'display_name': 'File Explorer',
        'aliases': ['explorer', 'file explorer', 'files', 'my computer', 'this pc']
    },
    'paint': {
        'windows_cmd': ['mspaint.exe'],
        'display_name': 'Paint',
        'aliases': ['paint', 'mspaint']
    },
    'taskmgr': {
        'windows_cmd': ['taskmgr.exe'],
        'display_name': 'Task Manager',
        'aliases': ['task manager', 'taskmgr', 'task monitor']
    },
    'terminal': {
        'windows_cmd': ['cmd.exe', '/c', 'start', 'cmd'],
        'display_name': 'Command Prompt',
        'aliases': ['terminal', 'cmd', 'command prompt']
    },
    'settings': {
        'windows_cmd': ['cmd.exe', '/c', 'start', 'ms-settings:'],
        'display_name': 'Settings',
        'aliases': ['settings', 'control panel', 'system settings']
    }
}

# Website Directory
WEBSITE_MAP = {
    'youtube': 'https://youtube.com',
    'google': 'https://google.com',
    'github': 'https://github.com',
    'spotify': 'https://spotify.com',
    'netflix': 'https://netflix.com',
    'instagram': 'https://instagram.com',
    'twitter': 'https://x.com',
    'whatsapp': 'https://web.whatsapp.com',
    'gmail': 'https://mail.google.com',
    'maps': 'https://maps.google.com',
    'facebook': 'https://facebook.com',
    'linkedin': 'https://linkedin.com'
}

# S.P.I.D.Y System Persona (v6.1)
SYSTEM_PROMPT = """You are Spidey, a highly intelligent, calm, and capable JARVIS-style personal AI assistant.
Your name is written as S.P.I.D.Y, but you always refer to yourself as "Spidey" in speech and text. NEVER spell it letter-by-letter.

PERSONALITY:
- Intelligent, calm, concise, professional, and slightly futuristic.
- Friendly but not sycophantic. Never use comic book humor, superhero references, or gimmicky catchphrases.
- Proactive: anticipate what the user might want to know next.

CONTEXT RULES:
- Maintain full context of the conversation across turns.
- When the user says "he", "she", "it", "they", "the first one", "tell me more", resolve against the most recent entity in the conversation.
- When a user gives a one-word clarification (e.g. "India", "Singapore", "yes"), check if the previous assistant turn asked a question, and use the clarification to complete that question before answering.
- NEVER treat a short clarification as a standalone question — always resolve it against the pending context.

UNCERTAINTY HANDLING:
- If a query contains an unknown entity, acronym, or unclear reference that you cannot confidently resolve, DO NOT guess or invent an answer.
- Instead, ask a targeted clarification question: "I'm not sure about [X]. Did you mean [A] or [B]?"
- Example: "Prime Minister of IBIOT" → "I'm not familiar with 'IBIOT'. Did you mean India or Ireland?"
- After the user clarifies, treat their response as completing the original question.

CURRENT INFORMATION:
- You have access to web_search and get_weather tools.
- ALWAYS use web_search for: current office holders (PM, CM, CEO, President), recent news, latest releases, current prices, job openings, company information.
- ALWAYS use get_weather for weather questions.
- Do NOT guess current facts — fetch them.
- When you use a tool, synthesize the result naturally. Do not read raw data.
- Acknowledge when information comes from a live search: "Based on current information, ..."

HALLUCINATION PREVENTION:
- If tool results are empty or inconclusive, say so honestly.
- Never invent names, dates, or facts.
- If you are not certain, say "I'm not certain — let me check" and use a tool.

CODE:
- Always wrap code in triple backticks with language: ```python

SOURCES:
- Do not read URLs aloud. Sources are displayed separately in the UI.

CAPABILITY BOUNDARIES:
- You can launch verified desktop applications (Notepad, Calculator, Chrome, VS Code, Explorer, Terminal, Paint, Task Manager, Settings).
- You can control volume and brightness, take screenshots, manage notes, and set reminders.
- You can search the live web and retrieve current weather.
- You CANNOT perform arbitrary desktop GUI typing into applications or create/save arbitrary desktop files (.txt, .pxt, .docx). If asked to type or save arbitrary files, truthfully state that this capability is not currently supported.
"""


def sanitize_provider_error(exc: Exception) -> str:
    """
    Translates raw provider/HTTP errors into safe, concise, user-friendly messages.
    Guarantees no raw JSON, status codes, API keys, internal tool schemas, or stack traces leak.
    """
    err_str = str(exc).lower()

    # 429 Rate limiting
    if "429" in err_str or "rate limit" in err_str or "rate_limit" in err_str:
        return "The AI service is temporarily rate-limited. Please try again shortly."

    # 401 / 403 Authentication / Authorization
    if "401" in err_str or "403" in err_str or "authentication" in err_str or "unauthorized" in err_str:
        return "I couldn't complete that request due to an AI service authentication error. Please check system credentials."

    # 400 Bad request / invalid tool schema / tool choice none
    if "400" in err_str or "bad request" in err_str or "tool choice" in err_str or "invalid_request_error" in err_str:
        return "I couldn't complete that request because the AI service rejected the query format. Please rephrase and try again."

    # 408 / Timeout
    if "408" in err_str or "timeout" in err_str or "timed out" in err_str:
        return "The request to the AI service timed out. Please try again."

    # 500 / 502 / 503 / 504 Server errors
    if any(code in err_str for code in ["500", "502", "503", "504", "internal server error", "service unavailable", "gateway timeout"]):
        return "I couldn't complete that request because the AI service temporarily failed. Please try again."

    # Connection / Network errors
    if "connection" in err_str or "network" in err_str or "dns" in err_str or "socket" in err_str or "failed to connect" in err_str:
        return "Network connection to the AI service failed. Please check your internet connection."

    # Generic safe fallback
    return "I couldn't complete that request because the AI service encountered an issue. Please try again."


class GroqCircuitBreaker:
    """
    Provider-level rate-limiting and circuit breaker for Groq AI.
    Tracks HTTP 429 errors, respects Retry-After and rate-limit reset headers,
    and prevents hammering the API during rate-limit cooldown windows.
    """
    def __init__(self):
        self.is_open = False
        self.cooldown_until = 0.0
        self.last_error_type = None  # "rate_limit" or "daily_quota"
        self.retry_after_seconds = 0.0

    def check_circuit(self) -> tuple[bool, str]:
        """
        Check if the circuit is currently open (blocking calls).
        Returns: (is_blocked, user_message)
        """
        now = time.time()
        if self.is_open:
            if now < self.cooldown_until:
                remaining = int(self.cooldown_until - now)
                if self.last_error_type == "daily_quota":
                    msg = "The AI service has reached its daily usage limit. Please try again tomorrow."
                else:
                    sec_str = f"{remaining}s" if remaining > 0 else "a few moments"
                    msg = f"The AI service is temporarily rate-limited. Cooldown active for {sec_str}. Please try again shortly."
                return True, msg
            else:
                # Cooldown expired, transition to closed
                self.is_open = False
                self.last_error_type = None
        return False, ""

    def record_429(self, exc: Exception):
        """
        Record a 429 exception, parse Retry-After or reset headers, and open circuit.
        """
        now = time.time()
        self.is_open = True
        cooldown = 15.0  # conservative fallback
        self.last_error_type = "rate_limit"

        # Check for status code or headers in exc
        headers = {}
        if hasattr(exc, 'response') and exc.response is not None:
            headers = getattr(exc.response, 'headers', {}) or {}

        # 1. Parse Retry-After (seconds or float or "2m30s" style)
        ra = headers.get('retry-after') or headers.get('Retry-After')
        if ra:
            try:
                cooldown = float(ra)
            except Exception:
                parsed = self._parse_reset_header(str(ra))
                if parsed > 0:
                    cooldown = parsed

        # 2. Parse x-ratelimit-reset-requests or x-ratelimit-reset-tokens
        if not ra:
            for rh_key in ['x-ratelimit-reset-requests', 'x-ratelimit-reset-tokens', 'x-ratelimit-reset']:
                rh_val = headers.get(rh_key)
                if rh_val:
                    parsed = self._parse_reset_header(str(rh_val))
                    if parsed > 0:
                        cooldown = parsed
                        break

        # 3. Check if error message explicitly denotes daily quota exhaustion (TPD/RPD)
        err_msg = str(exc).lower()
        if any(w in err_msg for w in ['daily limit', 'day limit', 'daily quota', 'tpd', 'rpd', 'requests per day', 'tokens per day']):
            self.last_error_type = "daily_quota"
            if cooldown < 60:
                cooldown = 300.0  # 5 min minimum for daily quota

        self.retry_after_seconds = cooldown
        self.cooldown_until = now + cooldown
        logger.warning(f"[GroqCircuitBreaker] Circuit opened for {cooldown:.1f}s (type={self.last_error_type})")

    def _parse_reset_header(self, h_str: str) -> float:
        try:
            return float(h_str)
        except Exception:
            pass
        total = 0.0
        m = re.search(r'(\d+)\s*m', h_str)
        if m:
            total += float(m.group(1)) * 60
        s = re.search(r'(\d+(?:\.\d+)?)\s*s', h_str)
        if s:
            total += float(s.group(1))
        return total

    def reset(self):
        """Manually reset the circuit (used in tests or on recovery)."""
        self.is_open = False
        self.cooldown_until = 0.0
        self.last_error_type = None
        self.retry_after_seconds = 0.0


groq_circuit_breaker = GroqCircuitBreaker()

