"""
S.P.I.D.Y v6.2 — Multi-Step Task Execution Engine
Handles multi-step user requests, execution plans, step dependency piping,
truthful verification, loop protection, and confirmation states.
"""

import re
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from config import GROQ_MODEL, GROQ_API_KEY, logger, groq_circuit_breaker
from agent.tools import AVAILABLE_TOOLS, get_last_sources, clear_last_sources
from agent.database import update_task_state, get_task_state

MAX_STEPS_LIMIT = 6

# Action verbs that indicate discrete executable steps
ACTION_VERBS = {
    'open', 'launch', 'start', 'run', 'close', 'kill',
    'search', 'find', 'lookup', 'look up', 'google',
    'weather', 'forecast', 'temperature',
    'screenshot', 'capture',
    'volume', 'mute', 'unmute',
    'summarize', 'summary',
    'save', 'note', 'add note', 'record',
    'remind', 'reminder', 'alarm'
}


def is_multi_step_request(text: str) -> bool:
    """
    Detect whether user text contains multiple distinct action intents.
    Distinguishes compound multi-step commands from single queries with 'and'.
    """
    if not text or not text.strip():
        return False

    t = text.lower().strip()

    # If it contains explicit sequential transition phrases
    sequential_markers = [
        ' and then ', ' then ', ' after that ', ' and also ',
        ' first ', ' followed by ', ' and save ', ' and tell me ',
        ' and summarize ', ' and open ', ' and capture '
    ]
    for marker in sequential_markers:
        if marker in t:
            return True

    # Check for conjunction 'and' or comma separating distinct action clauses
    segments = re.split(r'[,;]|\band\b', t)
    segments = [s.strip() for s in segments if s.strip()]

    if len(segments) < 2:
        return False

    # Count how many segments start with or strongly feature an action verb
    action_count = 0
    for seg in segments:
        words = seg.split()
        if not words:
            continue
        first_two = " ".join(words[:2])
        first_one = words[0]
        if first_one in ACTION_VERBS or first_two in ACTION_VERBS:
            action_count += 1
        elif any(verb in seg for verb in ['summarize', 'save to my notes', 'save to notes', 'tell me the weather', 'take a screenshot']):
            action_count += 1

    return action_count >= 2


def _plan_deterministic_patterns(text: str, conv_id: str) -> Optional[Dict[str, Any]]:
    """
    High-accuracy deterministic planner for standard multi-step patterns.
    Guarantees reliable execution even if Groq is offline or unavailable.
    """
    t = text.lower().strip()
    now_iso = datetime.now().isoformat()
    task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # Pattern A: Find/search <topic>, summarize, and save to notes
    # Example: "Find the latest AI news, summarize the important points, and save the summary to my notes."
    if ('search' in t or 'find' in t or 'news' in t) and ('summarize' in t or 'summary' in t) and ('note' in t or 'notes' in t):
        # Extract query topic
        query = "latest AI news"
        m_q = re.search(r'(?:find|search(?: for)?)\s+(?:the\s+)?(.*?)(?:,\s*|\s+and\s+)summarize', t)
        if m_q and m_q.group(1).strip():
            query = m_q.group(1).strip()
        elif 'ai news' in t:
            query = "latest AI news"
        elif 'openai news' in t:
            query = "latest OpenAI news"

        return {
            "task_id": task_id,
            "conversation_id": conv_id,
            "original_request": text,
            "goal": f"Search for '{query}', summarize findings, and save summary to notes",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": f"Search web for '{query}'",
                    "tool": "web_search",
                    "arguments": {"query": query},
                    "status": "PENDING",
                    "result": None,
                    "error": None,
                    "requires_confirmation": False,
                    "started_at": None,
                    "completed_at": None
                },
                {
                    "step_id": 2,
                    "description": "Summarize search findings into key points",
                    "tool": "summarize",
                    "arguments": {"input_from_step": 1, "focus": "important points and key announcements"},
                    "status": "PENDING",
                    "result": None,
                    "error": None,
                    "requires_confirmation": False,
                    "started_at": None,
                    "completed_at": None
                },
                {
                    "step_id": 3,
                    "description": "Save summary to user notes",
                    "tool": "save_note",
                    "arguments": {"input_from_step": 2},
                    "status": "PENDING",
                    "result": None,
                    "error": None,
                    "requires_confirmation": False,
                    "started_at": None,
                    "completed_at": None
                }
            ],
            "created_at": now_iso,
            "updated_at": now_iso
        }

    # Pattern B: Open <app> and tell me / get the weather
    # Example: "Open Notepad and tell me the current weather."
    if ('open ' in t or 'launch ' in t) and ('weather' in t or 'temperature' in t):
        # Extract app name
        app_name = "notepad"
        m_app = re.search(r'(?:open|launch)\s+([a-zA-Z0-9_\-\s]+?)(?:\s+and\s+|\s*,\s*)', t)
        if m_app:
            app_name = m_app.group(1).strip()
        elif 'calculator' in t:
            app_name = "calculator"
        elif 'chrome' in t:
            app_name = "chrome"

        # Extract city
        city = "Chennai"
        m_city = re.search(r'weather\s+(?:in|for)\s+([a-zA-Z\s]+)', t)
        if m_city:
            city = m_city.group(1).strip()

        return {
            "task_id": task_id,
            "conversation_id": conv_id,
            "original_request": text,
            "goal": f"Open {app_name} and check weather for {city}",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": f"Open application '{app_name}'",
                    "tool": "open_application",
                    "arguments": {"app_name": app_name},
                    "status": "PENDING",
                    "result": None,
                    "error": None,
                    "requires_confirmation": False,
                    "started_at": None,
                    "completed_at": None
                },
                {
                    "step_id": 2,
                    "description": f"Get current weather conditions for {city}",
                    "tool": "get_weather",
                    "arguments": {"city": city},
                    "status": "PENDING",
                    "result": None,
                    "error": None,
                    "requires_confirmation": False,
                    "started_at": None,
                    "completed_at": None
                }
            ],
            "created_at": now_iso,
            "updated_at": now_iso
        }

    # Pattern C: Take a screenshot and open <app>
    if 'screenshot' in t and ('open ' in t or 'launch ' in t):
        app_name = "notepad"
        if 'chrome' in t:
            app_name = "chrome"
        elif 'calculator' in t:
            app_name = "calculator"
        return {
            "task_id": task_id,
            "conversation_id": conv_id,
            "original_request": text,
            "goal": f"Capture screenshot and open {app_name}",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": "Capture screenshot of current screen",
                    "tool": "take_screenshot",
                    "arguments": {},
                    "status": "PENDING",
                    "result": None,
                    "error": None,
                    "requires_confirmation": False,
                    "started_at": None,
                    "completed_at": None
                },
                {
                    "step_id": 2,
                    "description": f"Open application '{app_name}'",
                    "tool": "open_application",
                    "arguments": {"app_name": app_name},
                    "status": "PENDING",
                    "result": None,
                    "error": None,
                    "requires_confirmation": False,
                    "started_at": None,
                    "completed_at": None
                }
            ],
            "created_at": now_iso,
            "updated_at": now_iso
        }

    # Pattern D: Open <app> and write/type/save file (Option B: Truthful unsupported)
    # Examples:
    # "Open not bad and write hello Spidey and save in the file as a demo."
    # "Open notepad and write the sentence ... and save it as Batre.pxt"
    # "Open notepad and type hello"
    has_app_open = ('open ' in t or 'launch ' in t or 'not bad' in t or 'notepad' in t)
    has_typing_or_file = any(w in t for w in ['write ', 'type ', 'save in the file', 'save to file', 'save as ']) or bool(re.search(r'\.[a-zA-Z0-9]{2,4}\b', t))
    # Exclude notes tool queries
    if ('save to my notes' not in t and 'save to notes' not in t) and has_app_open and has_typing_or_file:
        app_name = "notepad"
        if 'chrome' in t:
            app_name = "chrome"
        elif 'calculator' in t:
            app_name = "calculator"

        return {
            "task_id": task_id,
            "conversation_id": conv_id,
            "original_request": text,
            "goal": f"Open {app_name} and perform text/file automation",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": f"Open application '{app_name}'",
                    "tool": "open_application",
                    "arguments": {"app_name": app_name},
                    "status": "PENDING",
                    "result": None,
                    "error": None,
                    "requires_confirmation": False,
                    "started_at": None,
                    "completed_at": None
                },
                {
                    "step_id": 2,
                    "description": "Desktop typing and file saving",
                    "tool": "unsupported_desktop_action",
                    "arguments": {"app_name": app_name},
                    "status": "PENDING",
                    "result": None,
                    "error": None,
                    "requires_confirmation": False,
                    "started_at": None,
                    "completed_at": None
                }
            ],
            "created_at": now_iso,
            "updated_at": now_iso
        }

    return None


def create_task_plan(request_text: str, conv_id: str, groq_client=None) -> Dict[str, Any]:
    """
    Create a structured Multi-Step Task execution plan from a user request.
    Uses deterministic decomposition first for guaranteed precision,
    falling back to Groq LLM planner for novel combinations.
    """
    # 1. Check deterministic patterns
    det_plan = _plan_deterministic_patterns(request_text, conv_id)
    if det_plan:
        return det_plan

    now_iso = datetime.now().isoformat()
    task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # 2. LLM-based planner (if groq_client available and circuit not open)
    if groq_client:
        is_blocked, _ = groq_circuit_breaker.check_circuit()
        if not is_blocked:
            tools_list_desc = ", ".join([f"'{k}'" for k in AVAILABLE_TOOLS.keys()])
            prompt = f"""You are a multi-step task execution planner.
Decompose the following user request into a strictly ordered sequence of steps.
Available tools: {tools_list_desc}.
If a step needs the result of a previous step, use {{"input_from_step": <step_id>}} in arguments.
Max steps allowed: {MAX_STEPS_LIMIT}.

Return ONLY a valid JSON object matching this schema:
{{
  "goal": "<concise description of the overall task>",
  "steps": [
    {{
      "step_id": 1,
      "description": "<what this step does>",
      "tool": "<tool_name from available tools>",
      "arguments": {{"param": "val"}},
      "requires_confirmation": false
    }}
  ]
}}

User Request: {request_text}

JSON:"""
            try:
                resp = groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=350,
                    temperature=0.1
                )
                raw = (resp.choices[0].message.content or "").strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                data = json.loads(raw)

                steps = []
                for idx, s in enumerate(data.get("steps", [])[:MAX_STEPS_LIMIT]):
                    steps.append({
                        "step_id": idx + 1,
                        "description": s.get("description", f"Step {idx + 1}"),
                        "tool": s.get("tool", ""),
                        "arguments": s.get("arguments", {}),
                        "status": "PENDING",
                        "result": None,
                        "error": None,
                        "requires_confirmation": bool(s.get("requires_confirmation", False)),
                        "started_at": None,
                        "completed_at": None
                    })

                if steps:
                    return {
                        "task_id": task_id,
                        "conversation_id": conv_id,
                        "original_request": request_text,
                        "goal": data.get("goal", request_text),
                        "status": "PENDING",
                        "current_step_index": 0,
                        "steps": steps,
                        "created_at": now_iso,
                        "updated_at": now_iso
                    }
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    groq_circuit_breaker.record_429(e)
                logger.warning(f"[task_engine] LLM planning error: {e}")

    # 3. Fallback: Domain-aware single step (never blindly route desktop commands to web_search)
    t_req = request_text.lower()
    if any(w in t_req for w in ['notepad', 'calculator', 'chrome', 'vscode']) and any(w in t_req for w in ['write', 'type', 'file', 'save in the file', 'save to file']):
        fb_tool = "unsupported_desktop_action"
        fb_args = {}
        fb_desc = "Desktop typing and file saving"
    elif any(w in t_req for w in ['weather', 'forecast', 'temperature']):
        city = "Chennai"
        m_c = re.search(r'weather\s+(?:in|for)\s+([a-zA-Z\s]+)', t_req)
        if m_c:
            city = m_c.group(1).strip()
        fb_tool = "get_weather"
        fb_args = {"city": city}
        fb_desc = f"Get weather for {city}"
    elif any(w in t_req for w in ['news', 'search', 'find', 'who is', 'what is', 'latest', 'current', 'price', 'rate']):
        fb_tool = "web_search"
        fb_args = {"query": request_text}
        fb_desc = f"Search web for '{request_text}'"
    elif any(w in t_req for w in ['open ', 'launch ']):
        m_a = re.search(r'(?:open|launch)\s+([a-zA-Z0-9_\-]+)', t_req)
        app_n = m_a.group(1).strip() if m_a else "notepad"
        fb_tool = "open_application"
        fb_args = {"app_name": app_n}
        fb_desc = f"Open application '{app_n}'"
    else:
        # Truly unknown capability — do NOT use web_search
        fb_tool = "unsupported_desktop_action"
        fb_args = {}
        fb_desc = f"Unsupported capability: {request_text}"

    return {
        "task_id": task_id,
        "conversation_id": conv_id,
        "original_request": request_text,
        "goal": request_text,
        "status": "PENDING",
        "current_step_index": 0,
        "steps": [
            {
                "step_id": 1,
                "description": fb_desc,
                "tool": fb_tool,
                "arguments": fb_args,
                "status": "PENDING",
                "result": None,
                "error": None,
                "requires_confirmation": False,
                "started_at": None,
                "completed_at": None
            }
        ],
        "created_at": now_iso,
        "updated_at": now_iso
    }


def _resolve_step_arguments(args: dict, completed_steps: List[dict]) -> tuple[dict, Optional[str]]:
    """
    Resolve dependencies from completed steps into the arguments dictionary.
    Supports {"input_from_step": N} and string substitutions.
    Returns: (resolved_args, error_message)
    """
    resolved = dict(args)
    results_map = {s["step_id"]: s.get("result") for s in completed_steps if s.get("status") == "COMPLETED"}

    # Handle explicit "input_from_step"
    if "input_from_step" in resolved:
        dep_id = resolved.pop("input_from_step")
        if dep_id not in results_map or not results_map[dep_id]:
            return {}, f"Dependent step {dep_id} did not produce a valid output."
        dep_val = results_map[dep_id]
        # Map to 'text' parameter for summarize/save_note, or 'query'
        if "text" not in resolved and "content" not in resolved:
            resolved["text"] = dep_val

    # Handle string template references e.g. "{step.1.result}"
    for k, v in list(resolved.items()):
        if isinstance(v, str):
            for step_id, res_text in results_map.items():
                placeholder = f"{{step.{step_id}.result}}"
                if placeholder in v:
                    resolved[k] = v.replace(placeholder, str(res_text or ""))

    return resolved, None


TOOL_DOMAINS = {
    "open_application": "DESKTOP",
    "close_application": "DESKTOP",
    "take_screenshot": "DESKTOP",
    "control_volume": "SYSTEM",
    "get_weather": "WEATHER",
    "web_search": "WEB_SEARCH",
    "save_note": "NOTES",
    "get_notes": "NOTES",
    "set_reminder": "REMINDERS",
    "summarize": "SYNTHESIS",
    "unsupported_desktop_action": "DESKTOP_UNSUPPORTED",
}


def validate_plan_domains(task: Dict[str, Any]) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Validates that each planned step uses a tool compatible with the requested action.
    Blocks wrong-domain assignments (e.g. desktop typing mapped to web_search).
    Returns: (is_valid, error_code, error_message)
    """
    orig_req = task.get("original_request", "").lower()
    for s in task.get("steps", []):
        tool = s.get("tool", "")
        desc = (s.get("description", "") + " " + orig_req).lower()

        # Check if desktop typing / file writing is incorrectly assigned to web_search
        is_desktop_action = any(w in desc for w in ['notepad', 'write ', 'type ', 'save to file', 'save in the file', 'save as', '.txt', '.pxt'])
        if 'save to notes' in desc or 'save to my notes' in desc:
            is_desktop_action = False

        if is_desktop_action and tool == "web_search":
            return False, "WRONG_DOMAIN", f"Tool-domain mismatch: step '{s.get('description')}' requires desktop automation, but 'web_search' was selected."

    return True, None, None


def classify_tool_result(tool_name: str, result_str: str) -> tuple[str, str]:
    """
    Classify a tool result into:
    SUCCESS, FAILED, UNSUPPORTED, NO_RESULT, TIMEOUT
    Returns (status, detail_message)
    """
    if not result_str or not str(result_str).strip():
        return "FAILED", "Empty result returned by tool."

    lower = str(result_str).lower().strip()

    # 1. TIMEOUT
    if any(k in lower for k in ["timed out", "timeout", "timedout", "request timed out"]):
        return "TIMEOUT", result_str

    # 2. UNSUPPORTED
    if any(k in lower for k in [
        "not currently supported", "unsupported", "cannot perform arbitrary",
        "is not supported", "arbitrary desktop typing and file saving are not currently supported"
    ]):
        return "UNSUPPORTED", result_str

    # 3. NO_RESULT (specifically for information retrieval)
    if tool_name == "web_search" and any(k in lower for k in [
        "no wikipedia results found", "no results found", "live search failed",
        "could not retrieve", "no search query provided", "verified real-time financial sources are currently unreachable"
    ]):
        return "NO_RESULT", result_str

    # 4. FAILED
    if lower.startswith("error:") or lower.startswith("failed"):
        return "FAILED", result_str
    if "for security reasons" in lower and "not in the allowed list" in lower:
        return "FAILED", result_str
    if "screenshot failed" in lower:
        return "FAILED", result_str
    if "unknown tool" in lower or "unknown or unregistered tool" in lower:
        return "FAILED", result_str
    if "cannot close unrecognized application" in lower:
        return "FAILED", result_str
    if "permission denied" in lower:
        return "FAILED", result_str
    if "execution exception:" in lower:
        return "FAILED", result_str
    if "weather unavailable" in lower:
        return "FAILED", result_str

    # 5. Tool-specific failure checks
    if tool_name == "open_application" and "failed to open" in lower:
        return "FAILED", result_str
    if tool_name == "save_note" and lower.startswith("failed"):
        return "FAILED", result_str

    return "SUCCESS", result_str


def _is_truthful_failure(tool_name: str, result_str: str) -> bool:
    """
    Compatibility wrapper returning True if result is NOT SUCCESS.
    """
    status, _ = classify_tool_result(tool_name, result_str)
    return status != "SUCCESS"


def execute_task(task: Dict[str, Any], conv_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute a task sequentially, step by step, with dependency piping,
    truthful validation, loop protection, and SQLite persistence.
    """
    if not task or "steps" not in task:
        return {"status": "FAILED", "error": "Invalid task definition.", "reply": "Could not execute task: invalid plan."}

    conv_id = conv_id or task.get("conversation_id", "default")
    task["status"] = "RUNNING"
    task["updated_at"] = datetime.now().isoformat()

    steps = task["steps"]
    total_steps = len(steps)

    # Ensure all step dicts have default fields
    for s in steps:
        s.setdefault("result", None)
        s.setdefault("error", None)
        s.setdefault("status", "PENDING")
        s.setdefault("requires_confirmation", False)

    # Pre-execution Tool-Domain Validation
    is_valid_domain, domain_err_code, domain_err_msg = validate_plan_domains(task)
    if not is_valid_domain:
        task["status"] = "FAILED"
        if steps:
            steps[0]["status"] = "FAILED"
            steps[0]["error"] = domain_err_msg
        update_task_state(conv_id, task)
        return {
            "status": "FAILED",
            "task": task,
            "failed_step": steps[0]["step_id"] if steps else 1,
            "reply": f"Task stopped before execution: {domain_err_msg}"
        }

    # Hard loop protection check
    if total_steps > MAX_STEPS_LIMIT:
        task["status"] = "FAILED"
        err = f"Task exceeded maximum allowed steps limit ({MAX_STEPS_LIMIT})."
        update_task_state(conv_id, task)
        return {"status": "FAILED", "task": task, "reply": err}

    step_idx = task.get("current_step_index", 0)
    executed_in_this_run = 0

    while step_idx < total_steps:
        # Loop protection
        executed_in_this_run += 1
        if executed_in_this_run > MAX_STEPS_LIMIT + 1:
            task["status"] = "FAILED"
            err = "Execution stopped: loop limit exceeded."
            update_task_state(conv_id, task)
            return {"status": "FAILED", "task": task, "reply": err}

        step = steps[step_idx]
        task["current_step_index"] = step_idx
        task["updated_at"] = datetime.now().isoformat()

        # Check safety confirmation state
        if step.get("requires_confirmation") and step.get("status") != "CONFIRMED":
            step["status"] = "WAITING_CONFIRMATION"
            task["status"] = "WAITING_CONFIRMATION"
            update_task_state(conv_id, task)
            confirm_msg = (
                f"I am ready to perform step {step['step_id']}: '{step['description']}'. "
                "This action requires your confirmation. Would you like me to proceed?"
            )
            return {
                "status": "WAITING_CONFIRMATION",
                "task": task,
                "reply": confirm_msg,
                "pending_step": step["step_id"]
            }

        step["status"] = "RUNNING"
        step["started_at"] = datetime.now().isoformat()
        update_task_state(conv_id, task)

        # 1. Resolve arguments from prior steps
        prior_steps = steps[:step_idx]
        resolved_args, resolve_err = _resolve_step_arguments(step.get("arguments", {}), prior_steps)
        if resolve_err:
            step["status"] = "FAILED"
            step["error"] = resolve_err
            step["completed_at"] = datetime.now().isoformat()
            task["status"] = "FAILED"
            update_task_state(conv_id, task)
            return {
                "status": "FAILED",
                "task": task,
                "failed_step": step["step_id"],
                "reply": f"Task stopped at step {step['step_id']} ({step['description']}): {resolve_err}"
            }

        # 2. Execute registered tool
        tool_name = step.get("tool", "")
        if tool_name not in AVAILABLE_TOOLS:
            step["status"] = "FAILED"
            err_msg = f"Unknown or unregistered tool: '{tool_name}'"
            step["error"] = err_msg
            step["completed_at"] = datetime.now().isoformat()
            task["status"] = "FAILED"
            update_task_state(conv_id, task)
            return {
                "status": "FAILED",
                "task": task,
                "failed_step": step["step_id"],
                "reply": f"Task failed at step {step['step_id']}: {err_msg}"
            }

        try:
            tool_func = AVAILABLE_TOOLS[tool_name]["func"]
            tool_result = tool_func(resolved_args)
            result_str = str(tool_result)
        except Exception as ex:
            tool_result = f"Execution exception: {ex}"
            result_str = str(tool_result)

        # 3. Validate result using structured classification
        status_category, detail_msg = classify_tool_result(tool_name, result_str)
        if status_category != "SUCCESS":
            step["status"] = status_category
            step["error"] = detail_msg
            step["completed_at"] = datetime.now().isoformat()
            task["status"] = status_category
            # Dependent steps remain PENDING/SKIPPED
            update_task_state(conv_id, task)

            if status_category == "UNSUPPORTED":
                reply = f"Task stopped: Capability is not supported. {detail_msg}"
            elif status_category == "NO_RESULT":
                reply = f"Task stopped at step {step['step_id']} ({step['description']}): {detail_msg}"
            elif status_category == "TIMEOUT":
                reply = f"Task timed out at step {step['step_id']} ({step['description']}): {detail_msg}"
            else:
                reply = f"Task stopped because step {step['step_id']} ({step['description']}) failed: {detail_msg}"

            return {
                "status": status_category,
                "task": task,
                "failed_step": step["step_id"],
                "reply": reply
            }

        # Step succeeded
        step["status"] = "COMPLETED"
        step["result"] = result_str
        step["completed_at"] = datetime.now().isoformat()
        update_task_state(conv_id, task)

        step_idx += 1

    # Verify that all steps completed successfully
    if not all(s.get("status") == "COMPLETED" for s in steps):
        task["status"] = "FAILED"
        update_task_state(conv_id, task)
        return {
            "status": "FAILED",
            "task": task,
            "reply": "Task failed: Not all required steps completed successfully."
        }

    # All steps completed successfully
    task["status"] = "COMPLETED"
    task["current_step_index"] = total_steps
    task["updated_at"] = datetime.now().isoformat()
    update_task_state(conv_id, task)

    # Build final response synthesis
    completed_summaries = []
    for s in steps:
        res_snippet = s.get("result", "")
        if len(res_snippet) > 120:
            res_snippet = res_snippet[:120] + "..."
        completed_summaries.append(f"✓ {s['description']}: {res_snippet}")

    reply = f"Task completed successfully! ({task.get('goal', 'Requested operations')})\n\n" + "\n".join(completed_summaries)
    sources = get_last_sources()

    return {
        "status": "COMPLETED",
        "task": task,
        "reply": reply,
        "sources": sources
    }


def resume_task(conv_id: str, confirmation_input: str = "yes") -> Dict[str, Any]:
    """
    Resume a task that was paused in WAITING_CONFIRMATION or restart a task.
    """
    task = get_task_state(conv_id)
    if not task or not isinstance(task, dict) or "steps" not in task:
        return {"status": "NO_ACTIVE_TASK", "reply": "There is no active multi-step task to resume."}

    status = task.get("status")
    clean_input = confirmation_input.lower().strip()

    if status == "WAITING_CONFIRMATION":
        if any(w in clean_input for w in ["yes", "confirm", "proceed", "continue", "sure", "ok", "go ahead"]):
            # Mark the waiting step as CONFIRMED and resume execution
            step_idx = task.get("current_step_index", 0)
            if step_idx < len(task["steps"]):
                task["steps"][step_idx]["status"] = "CONFIRMED"
            return execute_task(task, conv_id)
        elif any(w in clean_input for w in ["no", "cancel", "stop", "abort", "don't"]):
            task["status"] = "CANCELLED"
            task["updated_at"] = datetime.now().isoformat()
            update_task_state(conv_id, task)
            return {"status": "CANCELLED", "reply": "Task was cancelled as requested.", "task": task}
        else:
            return {
                "status": "WAITING_CONFIRMATION",
                "reply": "Please reply 'yes' to proceed with the action or 'no' to cancel the task.",
                "task": task
            }

    # If already completed or failed and user says "start that task again" / "retry"
    if any(w in clean_input for w in ["again", "retry", "restart"]):
        for s in task.get("steps", []):
            s["status"] = "PENDING"
            s["result"] = None
            s["error"] = None
            s["started_at"] = None
            s["completed_at"] = None
        task["status"] = "PENDING"
        task["current_step_index"] = 0
        task["updated_at"] = datetime.now().isoformat()
        return execute_task(task, conv_id)

    return {"status": status, "reply": f"Active task is currently {status}.", "task": task}


def cancel_task(conv_id: str) -> Dict[str, Any]:
    """Cancel the current active task for the given conversation."""
    task = get_task_state(conv_id)
    if not task or not isinstance(task, dict) or "steps" not in task:
        return {"status": "NO_ACTIVE_TASK", "reply": "No active task found to cancel."}

    task["status"] = "CANCELLED"
    task["updated_at"] = datetime.now().isoformat()
    update_task_state(conv_id, task)
    return {"status": "CANCELLED", "reply": "Task has been cancelled.", "task": task}
