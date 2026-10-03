# Changelog & Version History

## [v6.2.1] - 2026-10-01 (Hardening & Reliability Milestone)

### Core Highlights
- **False Task-Success Prevention**: Tasks can only reach `COMPLETED` status when every required step actually succeeds. New structured status flow: `SUCCESS` | `FAILED` | `UNSUPPORTED` | `NO_RESULT` | `TIMEOUT`.
- **Domain-Aware Tool Validation (`validate_plan_domains`)**: Pre-execution check blocks wrong-domain tool assignments (e.g., desktop-typing step → web_search tool) before any execution begins.
- **Unsupported Desktop/File Handling**: Requests to open an app and type/save a file return truthful `UNSUPPORTED` response instead of silently routing to an unrelated tool.
- **Lenovo LOQ vs Workstation-Lock Safety**: Brand-query guard and strict lock-intent regex patterns prevent `"Lenovo LOQ laptop"` from triggering workstation lock. `"Lenovo"` + `"lock"` combination always returns a clarification request.
- **Entity/Voice Recovery**: `normalize_voice_text()` now corrects `"l o q"` → `"loq"`, `"l.o.q"` → `"loq"`, `"lenova"` → `"lenovo"`.
- **Provider Error Sanitization (`sanitize_provider_error`)**: HTTP 400/401/403/429/408/5xx and connection errors are mapped to safe user-facing messages; no raw Groq JSON, stack traces, or API keys are leaked.
- **Finance/Commodity Freshness Routing**: Gold/silver prices, market rates, stock prices, and revenue queries are classified as `'finance'` and routed to live DDG+News retrieval — never Wikipedia.
- **Source Integrity on Empty Finance Results**: Finance retrieval failure returns truthful `"Live market rate could not be retrieved"` with `sources: []`.
- **Capability Documentation Corrected**: `SYSTEM_PROMPT` updated with explicit `CAPABILITY BOUNDARIES` section; README updated to reflect actual supported vs. unsupported capabilities.
- **Version Alignment**: `app.py`, `test_spidy.py`, `SPIDY.html`, `app.js`, `CHANGELOG.md` all report `v6.2.1`.
- **Context Clarification & Confirmation State (`pending_clarification`)**: Added persistent, conversation-isolated clarification state preventing resurrection of older conversation context (e.g. Legion geographic queries) when confirming an entity ("Did you mean Lenovo LOQ laptop?" -> "Yes" -> confirms LOQ, never resurrects older Legion context).
- **Context Resolution Priority**: Context resolution explicitly prioritizes (1) Safety-critical command, (2) Active confirmation / pending clarification, (3) Active task continuation, (4) Explicitly referenced previous conversation request, (5) Multi-step tasks, (6) Deterministic commands, (7) Intent detection, (8) Sentiment analysis, (9) Conversational AI agent loop.
- **Previous Conversation Request Resolution**: Queries like "give me the response for the previous conversation" are safely inspected and resolved from conversation memory — never routed to web search.
- **Conversation Isolation & Clean Reset**: Pending clarification is strictly tied to `conversation_id`; New Chat (`DELETE /api/conversations/<id>`) clears all pending clarification state.
- **New Regression Test Suite (`test_spidy_621.py`)**: 41 targeted tests covering all hardening areas + 8 hotfix regression tests (Legion -> LOQ confirmation, yes/no, conversation isolation, previous conversation queries).
- **Groq Token & Quota Efficiency Hardening**:
  - Eliminated redundant `_extract_task_state` Groq LLM call; replaced with zero-cost local Python extraction (`_extract_task_state_local`).
  - Implemented selective tool binding (`get_selective_tool_schemas`) returning `None` (0 tool schemas, saving ~2,400 tokens) for pure knowledge queries, and strictly domain-relevant schemas for actionable requests.
  - Expanded greeting routing to guarantee 0 Groq calls for standard greetings ("hello spidey", "good morning", etc.).
  - Added `GroqCircuitBreaker` in `config.py` with dynamic `Retry-After` header parsing (seconds, float, and `"2m30s"` strings) and `x-ratelimit-reset` fallback, protecting TPM/TPD limits.
  - Preserved deterministic commands (Notepad, Calculator, Volume, Screenshot, Notes, Reminders) to operate 100% locally even while the Groq circuit breaker is open.
  - Reduced conversation history depth (`limit=6`), max tool turns (`2`), and capped completion tokens across router (`max_tokens=250`), context resolver (`max_tokens=180`), task engine (`max_tokens=350`), and summarizer (`max_tokens=250`).
  - Added `groq.circuit` status monitoring to `/api/status` endpoint for health check visibility.
  - New test suite `test_spidy_groq_efficiency.py` (36 tests) covering 0-call paths, selective binding, circuit breaker recovery, and credential safety.

- **Final Acceptance Fixes & Punctuation Hardening**:
  - Added missing `import re` to `agent/context_resolver.py` eliminating `NameError` crash on multi-turn continuation, jokes, and news requests.
  - Wrapped router pre-flight context resolution in `try...except` in `agent/router.py` with safe default context fallback, preventing unhandled 500 errors.
  - Fixed deterministic weather parser in `commands.py`: generic phrases ("what's the weather", "what is the weather today") default to "Chennai" rather than becoming the literal search city.
  - Permitted harmless trailing punctuation (`[.?!]*$`) in `app.py` and `commands.py` for explicit workstation lock commands ("Lock my computer.", "Please lock the pc.") while strictly keeping Lenovo/LOQ/Legion brand guards intact.
- **Final UI + Text Chat & Mojibake Hotfix**:
  - Fixed Groq HTTP 400 error on typed requests ("AI service rejected query format") by adding informational triggers (`'tell me about'`, `'about '`, `'know about'`) to `get_selective_tool_schemas`, updating Turn 2 system prompt to synthesize without calling tools, and implementing automatic retry recovery if an unconfigured tool call occurs.
  - Removed "🎤 Whisper heard: ..." debug message from chat UI (`static/app.js`), redirecting transcript to `console.log` so only the user's message is displayed.
  - Eliminated all UTF-8 mojibake (`â€”`, `ðŸ•·ï¸`, `ðŸ§ `, `ðŸŒ`, `âš™ï¸`, `ðŸ”—`) across `static/SPIDY.html` and `static/app.js`, restoring spider icon `🕷️`, brain `🧠`, globe `🌐`, gear `⚙️`, and em-dashes `—`.
  - Configured Flask `Response` with explicit `text/html; charset=utf-8` and `JSON_AS_ASCII=False` to prevent double-encoding corruption.
  - Added 19 new regression tests in `test_spidy_621.py` covering typed chat schema, Whisper debug removal, and UTF-8 encoding validation.

### Test Counts
- `test_spidy_groq_efficiency.py`: 36/36
- `test_spidy_621.py`: 72/72 (53 + 19 new)
- `test_task_engine.py`: 16/16
- `test_spidy.py`: 92/92
- **Total: 216/216 passing**

---

## [v6.2] - 2026-10-01 (Multi-Step Task Execution Engine)

### Core Highlights
- **Multi-Step Task Execution Engine (`agent/task_engine.py`)**: Structured sequential planner and executor decomposing compound natural-language commands into ordered dependency steps.
- **Dependency & Output Piping**: Seamless data handover between tools (e.g. `web_search` output -> `summarize` input -> `save_note` input).
- **Truthful Step Verification**: Strict result validation halting downstream dependent steps immediately if an upstream step fails.
- **Safety & Confirmation Pipeline**: Consequential/destructive steps enter `WAITING_CONFIRMATION` requiring explicit user affirmation ("yes", "confirm") before execution.
- **Loop & Step Protection**: Hard cap of 6 steps per plan and re-entrancy circuit breaker preventing infinite tool loops.
- **Task Continuation & Context Resolution**: Full support for reference continuations ("Save that to my notes", "Start that task again", "Cancel that task").
- **Tool Registry Expansion**: Added native tool wrappers in `AVAILABLE_TOOLS` for `save_note`, `get_notes`, `set_reminder`, and `summarize`.
- **Complete Test Coverage**: 16/16 new multi-step task engine tests + 92/92 regression tests passing (108/108 total).

---

## [v6.1] - 2026-10-01 (Validated Production Release)

### Core Highlights
- **92/92 Automated Tests**: Complete passing suite covering unit tests, deterministic routing, security whitelists, models, and integration benchmarks.
- **Live Web Retrieval**: Multi-tier freshness pipeline utilizing Google News RSS for live events/news and DuckDuckGo HTML for real-time web entity search, with Wikipedia REST summary fallback.
- **Source Integrity**: Real destination URLs and verified publisher attribution with zero hallucinated sources or phantom links on network failure.
- **Context Resolution**: Explicit conversation context resolver with pronoun resolution ("him", "her", "they"), continuation detection, and multi-turn state preservation.
- **Deterministic OS Commands**: Safe subprocess execution (shell=False) for Notepad, Calculator, Chrome, and system volume controls (up, down, mute, unmute).
- **Screenshot Capture**: Triple-fallback screen grab (PIL ImageGrab -> Win32 GDI BitBlt -> PowerShell .NET CopyFromScreen) with auto-desktop path resolution and truthful failure states.
- **Voice Pipeline**: Browser WebM audio recording + OpenAI Whisper GPU ASR (CUDA-accelerated) + direct FFmpeg conversion with KeyError prevention.
- **SQLite Memory**: Persistent conversation histories, isolated session threads, and long-term memory key-value storage.

---

## [v6.0] - 2026-09-30
- Introduced agent tool calling architecture with Groq `openai/gpt-oss-20b`.
- Added conversation memory database (`spidy_memory.db`) with conversation session management.
- Initial deterministic command parsing and security allowlisting.

---

## [v5.2.1] - 2026-09-30
- Fixed WebM audio conversion issue by invoking FFmpeg directly instead of pydub sample_width lookup.
- CUDA device selection fallback improvements.
