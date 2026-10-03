---
title: SPIDY Voice Assistant
emoji: 🕷️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# S.P.I.D.Y — Smart Personal Intelligent Digital Assistant for You

**Version: v6.2.1** | Voice-First AI Assistant | Python + Flask + Groq + Whisper

---

## Overview

S.P.I.D.Y (Spidey) is a locally-hosted voice and text assistant combining:
- OpenAI Whisper (CUDA-accelerated) for speech-to-text
- Groq LLM for conversational reasoning and agent tool-calling
- SQLite for persistent conversation memory
- A multi-step task execution engine for compound natural-language commands
- A structured freshness-routing pipeline for live web retrieval

---

## Supported Capabilities

### Voice & Conversation
- Browser microphone → WebM audio → Whisper ASR → text
- Multi-turn conversation memory (SQLite)
- Pronoun and context resolution across turns

### Live Web Retrieval
- Time-sensitive / current-information queries routed to live web (DDG HTML + Google News RSS)
- Finance/commodity queries (gold price, stock price, market rate) use dedicated finance retrieval — **never Wikipedia**
- General knowledge falls back to Wikipedia REST summary
- All sources returned as verified structured metadata (title, url, publisher, date)

### Multi-Step Task Execution
- Compound commands decomposed into ordered steps with dependency piping
- `PENDING` → `RUNNING` → `COMPLETED | FAILED | UNSUPPORTED | NO_RESULT | TIMEOUT | WAITING_CONFIRMATION`
- Task only reports `COMPLETED` when **every** step actually succeeds
- Consequential steps require explicit user confirmation before execution

### System Commands (Deterministic, Whitelisted)
| Command | Supported |
|---------|-----------|
| Open Notepad | ✅ |
| Open Calculator | ✅ |
| Open Chrome | ✅ |
| Volume up / down / mute / unmute | ✅ |
| Take screenshot (saves to Desktop) | ✅ |
| Lock workstation (explicit intent only) | ✅ |
| Set reminder | ✅ |
| Save / read notes | ✅ |
| Get weather | ✅ |
| Arbitrary desktop typing / GUI automation | ❌ Not supported |
| Saving arbitrary files to disk | ❌ Not supported |
| Controlling third-party application UI | ❌ Not supported |

> Unsupported capabilities return a clear, honest response — they are never silently rerouted.

### Safety & Security
- All OS commands run with `shell=False` against a strict allowlist
- Suspicious executables (e.g. `malware.exe`, `trojan_virus.exe`) are rejected with an error
- Workstation lock never triggers on brand/product queries (Lenovo LOQ, ASUS ROG, etc.)
- Provider errors (HTTP 429, 401, 500, timeouts) are sanitized to user-friendly messages — no raw JSON or API keys leaked

---

## Quick Start

### Requirements
- Python 3.10+
- FFmpeg on PATH (or set `FFMPEG_PATH` in `.env`)
- Groq API key

### Install
```bash
pip install -r requirements.txt
```

### Configure
Create a `.env` file (never commit this):
```
GROQ_API_KEY=your_key_here
FFMPEG_PATH=C:\path\to\ffmpeg\bin   # optional, auto-detected
```

### Run
```bash
python app.py
```
Open `http://localhost:5000` in your browser.

---

## Test Suite

```bash
python -m unittest test_spidy.py                # 92 regression tests
python -m unittest test_task_engine.py          # 16 task engine tests
python -m unittest test_spidy_621.py            # 72 v6.2.1 hardening, clarification & acceptance tests
python -m unittest test_spidy_groq_efficiency.py # 36 Groq efficiency & circuit breaker tests
```

**Total: 216/216 passing**

---

## Architecture

```
Browser (SPIDY.html / app.js)
    ↓ POST /api/chat
app.py
    ├─ Priority 0: Task Engine (multi-step, continuation, confirmation)
    ├─ Priority 1: Deterministic command parser (OS commands)
    ├─ Priority 2: Intent detector (HuggingFace)
    ├─ Priority 3: Sentiment analyzer
    └─ Priority 4: Groq agent loop (tool-calling LLM)
           ├─ agent/router.py       — conversation routing + Groq calls
           ├─ agent/tools.py        — AVAILABLE_TOOLS registry
           ├─ agent/task_engine.py  — multi-step planner + executor
           ├─ agent/context_resolver.py — pronoun/freshness/continuation
           └─ agent/database.py     — SQLite memory
```

---

## Version History

See [CHANGELOG.md](CHANGELOG.md) for full version history.

| Version | Date | Highlights |
|---------|------|-----------|
| v6.2.1 | 2026-10-01 | Hardening: false-success prevention, domain validation, unsupported-capability handling, Lenovo LOQ safety, provider error sanitization, finance routing, source integrity |
| v6.2 | 2026-10-01 | Multi-step task execution engine (108/108 tests) |
| v6.1 | 2026-10-01 | Live web retrieval, source integrity, voice pipeline, SQLite memory (92/92 tests) |
| v6.0 | 2026-09-30 | Agent tool-calling architecture, Groq integration |