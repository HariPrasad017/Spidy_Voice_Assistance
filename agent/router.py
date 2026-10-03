"""
S.P.I.D.Y v6.2.1 — Agent Router (Optimized for Groq Token & Quota Efficiency)
Full pipeline:
  conversation history → selective context resolution → local task state
  → selective tool binding → LLM reasoning → response → memory update
"""

import json
import logging
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import GROQ_MODEL, SYSTEM_PROMPT, logger, sanitize_provider_error, groq_circuit_breaker
from agent.database import (
    get_recent_messages, add_message, create_conversation,
    get_task_state, update_task_state
)
from agent.tools import AVAILABLE_TOOLS, get_tool_schemas, get_last_sources, clear_last_sources
from agent.context_resolver import resolve_context, needs_freshness


# ─── Zero-cost local task-state extraction (NO Groq calls) ────────────────────

def _extract_task_state_local(user_text: str, current_task: dict | None) -> dict | None:
    """Zero-cost Python/regex task state extraction without calling Groq."""
    if not current_task and not any(w in user_text.lower() for w in ['job', 'role', 'internship', 'opening']):
        return None

    t = user_text.lower()
    res = dict(current_task) if current_task else {
        "task_type": "job_search",
        "company": None,
        "role": None,
        "location": None,
        "topic": None,
        "active": True
    }
    # Match company: at <Company>
    m_comp = re.search(r'\bat\s+([A-Za-z0-9]+)', user_text)
    if m_comp:
        res["company"] = m_comp.group(1).title()
    # Match location: in <Location>
    m_loc = re.search(r'\bin\s+([A-Za-z0-9\s]+)', user_text)
    if m_loc:
        loc = m_loc.group(1).strip().split()[0].title()
        if loc.lower() not in ['india', 'singapore', 'us', 'usa', 'chennai', 'bangalore', 'london', 'remote']:
            loc = m_loc.group(1).strip().title()
        res["location"] = loc
    # Match role: e.g. "ML roles", "python developer"
    m_role = re.search(r'\b(ml|ai|machine learning|python|backend|frontend|fullstack|software|data scientist)\b', t)
    if m_role:
        res["role"] = m_role.group(0).upper() if m_role.group(0) in ['ml', 'ai'] else m_role.group(0).title()

    return res


def _build_task_context_block(task_state: dict | None) -> str:
    """Format active task state into a clear text block for the system prompt."""
    if not task_state:
        return ""
    lines = ["ACTIVE TASK CONTEXT:"]
    if task_state.get("task_type"):
        lines.append(f"  Task: {task_state['task_type']}")
    if task_state.get("company"):
        lines.append(f"  Company: {task_state['company']}")
    if task_state.get("role"):
        lines.append(f"  Role filter: {task_state['role']}")
    if task_state.get("location"):
        lines.append(f"  Location filter: {task_state['location']}")
    if task_state.get("topic"):
        lines.append(f"  Topic: {task_state['topic']}")
    return "\n".join(lines)


# ─── Selective Tool Schema Binding (Token Optimization) ─────────────────────────

def get_selective_tool_schemas(query: str, requires_web: bool = False) -> list | None:
    """
    Selectively binds only relevant tool schemas based on query intent.
    Pure knowledge/conversational requests get None (saves ~2,400 input tokens!).
    """
    q = query.lower().strip()
    schemas = get_tool_schemas()
    schema_map = {s["function"]["name"]: s for s in schemas}

    # 1. Weather requests -> get_weather only
    if any(w in q for w in ['weather', 'forecast', 'temperature', 'rain', 'climate', 'humidity', 'wind speed']):
        return [schema_map["get_weather"]] if "get_weather" in schema_map else schemas

    # 2. Freshness / live search / information requests -> web_search only
    if requires_web or any(w in q for w in [
        'latest', 'current', 'recent', 'today', 'news', 'price', 'rate',
        'who is the current', 'who is the present', 'who won', 'ceo of',
        'search', 'find', 'lookup', 'look up', 'google',
        'tell me about', 'know about', 'about ', 'info on', 'information about'
    ]):
        return [schema_map["web_search"]] if "web_search" in schema_map else schemas

    # 3. Notes requests -> notes tools only
    if any(w in q for w in ['note', 'notes', 'memo']):
        selected = [schema_map[k] for k in ["get_notes", "save_note"] if k in schema_map]
        return selected if selected else schemas

    # 4. Reminders requests -> reminder tool only
    if any(w in q for w in ['remind', 'reminder', 'alarm']):
        return [schema_map["set_reminder"]] if "set_reminder" in schema_map else schemas

    # 5. Application open/close requests -> app tools only
    if any(w in q for w in ['open ', 'launch ', 'close ', 'quit ', 'kill ']):
        selected = [schema_map[k] for k in ["open_application", "close_application"] if k in schema_map]
        return selected if selected else schemas

    # 6. Screenshot / Volume requests -> hardware tools only
    if any(w in q for w in ['screenshot', 'capture screen', 'volume', 'mute', 'unmute']):
        selected = [schema_map[k] for k in ["take_screenshot", "control_volume"] if k in schema_map]
        return selected if selected else schemas

    # 7. Pure conversational / explanation / general knowledge requests:
    # e.g. "What is machine learning?", "Explain gravity", "Who was Napoleon?", "Tell me a joke"
    # Returns None to completely omit tool schemas (saving ~2,400 input tokens).
    return None


# ─── Main Router ─────────────────────────────────────────────────────────────────

def route_conversation(user_text: str, conv_id: str, groq_client) -> dict:
    """
    Main agent entry point — optimized for minimum Groq calls and token efficiency.

    Returns {
        'reply': str,
        'action': str | None,
        'sources': list,        # [{title, url, source}]
        'resolved_query': str   # what we actually answered
    }
    """
    if not groq_client:
        return {
            "reply": "I'm ready for local commands, but the Groq API key isn't configured for AI conversations.",
            "action": None,
            "sources": [],
            "resolved_query": user_text
        }

    # ── 0. Circuit Breaker Check ──────────────────────────────────────────────
    is_blocked, block_msg = groq_circuit_breaker.check_circuit()
    if is_blocked:
        return {
            "reply": block_msg,
            "action": None,
            "sources": [],
            "resolved_query": user_text
        }

    create_conversation(conv_id)
    clear_last_sources()

    # ── 1. Load conversation history and task state ───────────────────────────
    history = get_recent_messages(conv_id, limit=6)
    current_task = get_task_state(conv_id)

    # ── 2. Context resolution (optimized to only call Groq when referent exists)
    try:
        ctx = resolve_context(user_text, history, groq_client, conv_id)
    except Exception as e:
        logger.error(f"[Router] Context resolution unexpected error: {e}", exc_info=True)
        ctx = {
            "resolved_query": user_text,
            "active_topic": None,
            "active_entity": None,
            "pending_clarification": False,
            "requires_web_search": needs_freshness(user_text),
            "context_summary": "",
            "is_continuation": False
        }
    resolved_query = ctx.get("resolved_query", user_text)
    requires_web = ctx.get("requires_web_search", False)
    context_summary = ctx.get("context_summary", "")
    is_continuation = ctx.get("is_continuation", False)

    logger.info(f"[Router] Resolved: '{resolved_query}' | web={requires_web} | cont={is_continuation}")

    # ── 3. Zero-cost local task state update (NO Groq call) ───────────────────
    new_task = _extract_task_state_local(user_text, current_task)
    if new_task != current_task:
        update_task_state(conv_id, new_task)
        current_task = new_task
        logger.info(f"[Router] Task state updated locally: {current_task}")

    task_block = _build_task_context_block(current_task)

    # ── 4. Build system prompt with injected context ──────────────────────────
    augmented_system = SYSTEM_PROMPT
    if context_summary:
        augmented_system += f"\n\nCONVERSATION CONTEXT: {context_summary}"
    if task_block:
        augmented_system += f"\n\n{task_block}"
    if requires_web:
        augmented_system += "\n\nIMPORTANT: This query requires CURRENT information. You MUST use the web_search tool."

    # ── 5. Build message list ─────────────────────────────────────────────────
    messages = [{"role": "system", "content": augmented_system}]
    messages.extend(history)

    effective_query = resolved_query if resolved_query != user_text else user_text
    messages.append({"role": "user", "content": effective_query})

    # Select only the required tool schemas (or None for pure conversational queries)
    tool_schemas = get_selective_tool_schemas(effective_query, requires_web=requires_web)
    action_taken = None

    try:
        # ── 6. Agent Loop with Selective Tools ────────────────────────────────
        max_tool_turns = 2
        turn = 0
        final_reply = ""

        while turn < max_tool_turns:
            turn += 1

            # Prepare call arguments
            call_kwargs = {
                "model": GROQ_MODEL,
                "messages": messages,
                "max_tokens": 250,
                "temperature": 0.7
            }
            # Only attach tools in Turn 1 if tool schemas are needed
            if turn == 1 and tool_schemas:
                call_kwargs["tools"] = tool_schemas
                call_kwargs["tool_choice"] = "auto"

            response = groq_client.chat.completions.create(**call_kwargs)
            msg = response.choices[0].message

            if msg.tool_calls:
                tool_call = msg.tool_calls[0]
                t_name = tool_call.function.name
                raw_args = tool_call.function.arguments or "{}"
                try:
                    t_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    t_args = {}

                logger.info(f"[Router] Tool: {t_name} | args: {t_args}")

                tool_result = f"Tool '{t_name}' not found in registry."
                if t_name in AVAILABLE_TOOLS:
                    try:
                        tool_result = AVAILABLE_TOOLS[t_name]["func"](t_args)
                    except Exception as te:
                        tool_result = f"Tool execution error: {te}"
                        logger.error(f"[Router] Tool error ({t_name}): {te}")

                action_taken = f"Used tool: {t_name}"
                logger.info(f"[Router] Tool result (truncated): {str(tool_result)[:300]}")

                # Append tool exchange to messages
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [{
                        "id": tool_call.id,
                        "type": "function",
                        "function": {"name": t_name, "arguments": raw_args}
                    }]
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": t_name,
                    "content": str(tool_result)
                })
                # Proceed to Turn 2 for synthesis.
                # IMPORTANT: Update system message so model synthesizes from tool results
                # and does NOT try to call tools again (which causes Groq 400 errors).
                messages[0] = {
                    "role": "system",
                    "content": (
                        SYSTEM_PROMPT
                        + "\n\nThe required information has been retrieved above. "
                        "Answer the user's question directly and concisely based on the tool results. "
                        "Do NOT call any more tools."
                    )
                }
            else:
                final_reply = (msg.content or "").strip()
                break

        if not final_reply:
            # Fallback synthesis if tool was executed but loop exited
            synth_kwargs = {
                "model": GROQ_MODEL,
                "messages": messages + [{"role": "user", "content": "Please summarize your findings into a concise, direct response."}],
                "max_tokens": 250,
                "temperature": 0.7
            }
            synth_resp = groq_client.chat.completions.create(**synth_kwargs)
            final_reply = (synth_resp.choices[0].message.content or "").strip()

        if not final_reply:
            final_reply = "I'm here. What would you like to know?"

        # ── 8. Persist ────────────────────────────────────────────────────────
        add_message(conv_id, "user", user_text)
        add_message(conv_id, "assistant", final_reply)

        sources = get_last_sources()

        return {
            "reply": final_reply,
            "action": action_taken,
            "sources": sources,
            "resolved_query": resolved_query
        }

    except Exception as e:
        logger.error(f"[Router] Error: {e}", exc_info=True)
        # Catch 429 and record in circuit breaker
        if "429" in str(e) or "rate" in str(e).lower() or getattr(e, 'status_code', None) == 429:
            groq_circuit_breaker.record_429(e)
            is_bl, bl_msg = groq_circuit_breaker.check_circuit()
            safe_reply = bl_msg if is_bl else sanitize_provider_error(e)
        elif "tool choice is none" in str(e).lower() or "tool_use_failed" in str(e).lower():
            logger.info("[Router] Model attempted tool call with no tools bound. Retrying with web_search...")
            try:
                schemas = get_tool_schemas()
                web_schema = [s for s in schemas if s["function"]["name"] == "web_search"]
                retry_resp = groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=messages,
                    tools=web_schema,
                    tool_choice="auto",
                    max_tokens=250,
                    temperature=0.7
                )
                r_msg = retry_resp.choices[0].message
                if r_msg.tool_calls:
                    tc = r_msg.tool_calls[0]
                    t_name = tc.function.name
                    raw_args = tc.function.arguments or "{}"
                    try:
                        t_args = json.loads(raw_args)
                    except Exception:
                        t_args = {}
                    t_res = AVAILABLE_TOOLS[t_name]["func"](t_args) if t_name in AVAILABLE_TOOLS else ""
                    messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": t_name, "arguments": raw_args}}]})
                    messages.append({"role": "tool", "tool_call_id": tc.id, "name": t_name, "content": str(t_res)})
                    messages[0] = {"role": "system", "content": SYSTEM_PROMPT + "\n\nAnswer the user's question directly based on the results above. Do NOT call tools."}
                    synth = groq_client.chat.completions.create(model=GROQ_MODEL, messages=messages, max_tokens=250, temperature=0.7)
                    safe_reply = (synth.choices[0].message.content or "").strip()
                else:
                    safe_reply = (r_msg.content or "").strip()
                if safe_reply:
                    add_message(conv_id, "user", user_text)
                    add_message(conv_id, "assistant", safe_reply)
                    return {"reply": safe_reply, "action": "Used tool: web_search", "sources": get_last_sources(), "resolved_query": resolved_query}
            except Exception as retry_err:
                logger.error(f"[Router] Tool recovery retry failed: {retry_err}")
                safe_reply = sanitize_provider_error(e)
        else:
            safe_reply = sanitize_provider_error(e)

        return {
            "reply": safe_reply,
            "action": None,
            "sources": [],
            "resolved_query": user_text
        }
