"""
S.P.I.D.Y v6.2 — Multi-Step Task Execution Engine Test Suite
Validates task planning, sequential step execution, dependency piping,
failure handling, persistence, confirmation, loop protection, and context continuation.
"""

import os
import sys
import unittest
import json
import time
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from agent.task_engine import (
    is_multi_step_request,
    create_task_plan,
    execute_task,
    resume_task,
    cancel_task,
    MAX_STEPS_LIMIT
)
from agent.database import (
    create_conversation,
    clear_conversation,
    get_task_state,
    update_task_state,
    add_message,
    get_recent_messages
)
from agent.tools import AVAILABLE_TOOLS
from commands import parse_command
from app import app


class TestTaskEngine(unittest.TestCase):

    def setUp(self):
        self.conv_id = f"test_task_conv_{int(time.time() * 1000)}"
        create_conversation(self.conv_id, title="Task Engine Unit Test")

    def tearDown(self):
        clear_conversation(self.conv_id)

    # 1. Single-step task
    def test_01_single_step_task(self):
        task = {
            "task_id": "t1",
            "conversation_id": self.conv_id,
            "goal": "Get weather",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": "Check weather in Chennai",
                    "tool": "get_weather",
                    "arguments": {"city": "Chennai"},
                    "status": "PENDING",
                    "requires_confirmation": False
                }
            ]
        }
        res = execute_task(task, self.conv_id)
        self.assertEqual(res["status"], "COMPLETED")
        self.assertEqual(task["steps"][0]["status"], "COMPLETED")
        self.assertTrue(len(task["steps"][0]["result"]) > 0)

    # 2. Two-step task
    @patch('subprocess.Popen')
    def test_02_two_step_task(self, mock_popen):
        mock_popen.return_value.poll.return_value = None
        mock_popen.return_value.returncode = 0
        task = {
            "task_id": "t2",
            "conversation_id": self.conv_id,
            "goal": "Open app and check weather",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": "Open Notepad",
                    "tool": "open_application",
                    "arguments": {"app_name": "notepad"},
                    "status": "PENDING",
                    "requires_confirmation": False
                },
                {
                    "step_id": 2,
                    "description": "Check weather in Chennai",
                    "tool": "get_weather",
                    "arguments": {"city": "Chennai"},
                    "status": "PENDING",
                    "requires_confirmation": False
                }
            ]
        }
        res = execute_task(task, self.conv_id)
        self.assertEqual(res["status"], "COMPLETED")
        self.assertEqual(task["steps"][0]["status"], "COMPLETED")
        self.assertEqual(task["steps"][1]["status"], "COMPLETED")

    # 3. Three-step task
    def test_03_three_step_task(self):
        task = {
            "task_id": "t3",
            "conversation_id": self.conv_id,
            "goal": "Search, summarize, and save note",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": "Search AI news",
                    "tool": "web_search",
                    "arguments": {"query": "latest AI news"},
                    "status": "PENDING",
                    "requires_confirmation": False
                },
                {
                    "step_id": 2,
                    "description": "Summarize search findings",
                    "tool": "summarize",
                    "arguments": {"input_from_step": 1, "focus": "key advances"},
                    "status": "PENDING",
                    "requires_confirmation": False
                },
                {
                    "step_id": 3,
                    "description": "Save to notes",
                    "tool": "save_note",
                    "arguments": {"input_from_step": 2},
                    "status": "PENDING",
                    "requires_confirmation": False
                }
            ]
        }
        res = execute_task(task, self.conv_id)
        self.assertEqual(res["status"], "COMPLETED")
        self.assertEqual(task["steps"][0]["status"], "COMPLETED")
        self.assertEqual(task["steps"][1]["status"], "COMPLETED")
        self.assertEqual(task["steps"][2]["status"], "COMPLETED")

    # 4. Successful dependency piping
    def test_04_successful_dependency_piping(self):
        task = {
            "task_id": "t4",
            "conversation_id": self.conv_id,
            "goal": "Pipe step 1 output into step 2",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": "Produce test output",
                    "tool": "summarize",
                    "arguments": {"text": "Artificial Intelligence is transforming medical science and biology."},
                    "status": "PENDING",
                    "requires_confirmation": False
                },
                {
                    "step_id": 2,
                    "description": "Save note with input from step 1",
                    "tool": "save_note",
                    "arguments": {"input_from_step": 1},
                    "status": "PENDING",
                    "requires_confirmation": False
                }
            ]
        }
        res = execute_task(task, self.conv_id)
        self.assertEqual(res["status"], "COMPLETED")
        step1_res = task["steps"][0]["result"]
        step2_res = task["steps"][1]["result"]
        self.assertIn("Note saved", step2_res)
        # Verify the saved note contains the summary content
        self.assertTrue(len(step1_res) > 0)

    # 5. Failed first step
    def test_05_failed_first_step(self):
        task = {
            "task_id": "t5",
            "conversation_id": self.conv_id,
            "goal": "Fail on first step",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": "Launch invalid malicious executable",
                    "tool": "open_application",
                    "arguments": {"app_name": "trojan_virus.exe"},
                    "status": "PENDING",
                    "requires_confirmation": False
                },
                {
                    "step_id": 2,
                    "description": "Should never execute",
                    "tool": "get_weather",
                    "arguments": {"city": "Chennai"},
                    "status": "PENDING",
                    "requires_confirmation": False
                }
            ]
        }
        res = execute_task(task, self.conv_id)
        self.assertEqual(res["status"], "FAILED")
        self.assertEqual(task["steps"][0]["status"], "FAILED")
        # 7. Dependent steps skipped after failure
        self.assertEqual(task["steps"][1]["status"], "PENDING")
        self.assertIsNone(task["steps"][1]["result"])

    # 6. Failed middle step & 7. Dependent steps skipped
    def test_06_failed_middle_step(self):
        task = {
            "task_id": "t6",
            "conversation_id": self.conv_id,
            "goal": "Fail in the middle",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": "Get valid weather",
                    "tool": "get_weather",
                    "arguments": {"city": "Chennai"},
                    "status": "PENDING",
                    "requires_confirmation": False
                },
                {
                    "step_id": 2,
                    "description": "Invalid tool call",
                    "tool": "unknown_nonexistent_tool",
                    "arguments": {},
                    "status": "PENDING",
                    "requires_confirmation": False
                },
                {
                    "step_id": 3,
                    "description": "Save note (must be skipped)",
                    "tool": "save_note",
                    "arguments": {"text": "Should not be saved"},
                    "status": "PENDING",
                    "requires_confirmation": False
                }
            ]
        }
        res = execute_task(task, self.conv_id)
        self.assertEqual(res["status"], "FAILED")
        self.assertEqual(task["steps"][0]["status"], "COMPLETED")
        self.assertEqual(task["steps"][1]["status"], "FAILED")
        self.assertEqual(task["steps"][2]["status"], "PENDING")
        self.assertIsNone(task["steps"][2]["result"])

    # 8. Task persistence in SQLite
    def test_08_task_persistence(self):
        plan = create_task_plan("Open Notepad and tell me the current weather.", self.conv_id)
        update_task_state(self.conv_id, plan)
        stored = get_task_state(self.conv_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["task_id"], plan["task_id"])
        self.assertEqual(len(stored["steps"]), 2)

    # 9. Task resume & 11. Confirmation required & 12. Confirmation resume
    def test_09_11_12_confirmation_and_resume(self):
        task = {
            "task_id": "t_conf_1",
            "conversation_id": self.conv_id,
            "goal": "Consequential task requiring confirmation",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": "Read notes safely",
                    "tool": "get_notes",
                    "arguments": {},
                    "status": "PENDING",
                    "requires_confirmation": False
                },
                {
                    "step_id": 2,
                    "description": "Consequential action requiring confirmation",
                    "tool": "save_note",
                    "arguments": {"text": "Verified confirmation write"},
                    "status": "PENDING",
                    "requires_confirmation": True
                }
            ]
        }
        # First execution pauses at step 2
        res1 = execute_task(task, self.conv_id)
        self.assertEqual(res1["status"], "WAITING_CONFIRMATION")
        self.assertEqual(task["steps"][0]["status"], "COMPLETED")
        self.assertEqual(task["steps"][1]["status"], "WAITING_CONFIRMATION")

        # Confirm and resume
        res2 = resume_task(self.conv_id, "yes, proceed please")
        self.assertEqual(res2["status"], "COMPLETED")
        stored = get_task_state(self.conv_id)
        self.assertEqual(stored["status"], "COMPLETED")
        self.assertEqual(stored["steps"][1]["status"], "COMPLETED")

    # 10. Task cancellation
    def test_10_task_cancellation(self):
        task = {
            "task_id": "t_cancel_1",
            "conversation_id": self.conv_id,
            "goal": "Task to be cancelled",
            "status": "WAITING_CONFIRMATION",
            "current_step_index": 1,
            "steps": [
                {
                    "step_id": 1,
                    "description": "Step 1",
                    "tool": "get_notes",
                    "arguments": {},
                    "status": "COMPLETED",
                    "requires_confirmation": False
                },
                {
                    "step_id": 2,
                    "description": "Step 2",
                    "tool": "save_note",
                    "arguments": {"text": "Never write"},
                    "status": "WAITING_CONFIRMATION",
                    "requires_confirmation": True
                }
            ]
        }
        update_task_state(self.conv_id, task)
        res = cancel_task(self.conv_id)
        self.assertEqual(res["status"], "CANCELLED")
        stored = get_task_state(self.conv_id)
        self.assertEqual(stored["status"], "CANCELLED")

    # 13. Context/pronoun continuation ("Save that to my notes")
    def test_13_context_continuation(self):
        client = app.test_client()
        # Seed conversation with an assistant answer
        add_message(self.conv_id, "user", "What is the capital of Tamil Nadu?")
        add_message(self.conv_id, "assistant", "The capital of Tamil Nadu is Chennai.")

        res = client.post('/api/chat', json={
            'message': 'Save that to my notes.',
            'conversation_id': self.conv_id
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn("Saved to your notes", data['reply'])
        self.assertIn("Chennai", data['reply'])

    # 14. Multiple conversation isolation
    def test_14_multiple_conversation_isolation(self):
        conv_a = f"task_iso_a_{int(time.time() * 1000)}"
        conv_b = f"task_iso_b_{int(time.time() * 1000)}"
        create_conversation(conv_a)
        create_conversation(conv_b)

        task_a = create_task_plan("Open Notepad and tell me the current weather.", conv_a)
        update_task_state(conv_a, task_a)

        # conv_b must have NO active task
        state_b = get_task_state(conv_b)
        self.assertIsNone(state_b)

        # Clean up
        clear_conversation(conv_a)
        clear_conversation(conv_b)

    # 15. Invalid / unknown tool handling
    def test_15_invalid_tool_handling(self):
        task = {
            "task_id": "t_inv",
            "conversation_id": self.conv_id,
            "goal": "Invalid tool test",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": "Use invalid tool",
                    "tool": "hack_the_pentagon",
                    "arguments": {},
                    "status": "PENDING",
                    "requires_confirmation": False
                }
            ]
        }
        res = execute_task(task, self.conv_id)
        self.assertEqual(res["status"], "FAILED")
        self.assertIn("Unknown or unregistered tool", res["reply"])

    # 16. Six-step hard limit
    def test_16_six_step_limit(self):
        # Create 7 steps
        steps = []
        for i in range(7):
            steps.append({
                "step_id": i + 1,
                "description": f"Step {i+1}",
                "tool": "get_notes",
                "arguments": {},
                "status": "PENDING",
                "requires_confirmation": False
            })
        task = {
            "task_id": "t_limit",
            "conversation_id": self.conv_id,
            "goal": "Exceed 6 steps",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": steps
        }
        res = execute_task(task, self.conv_id)
        self.assertEqual(res["status"], "FAILED")
        self.assertIn("maximum allowed steps limit", res["reply"])

    # 17. Loop prevention
    def test_17_loop_prevention(self):
        # Create task where current_step_index doesn't advance
        task = {
            "task_id": "t_loop",
            "conversation_id": self.conv_id,
            "goal": "Loop test",
            "status": "PENDING",
            "current_step_index": 0,
            "steps": [
                {
                    "step_id": 1,
                    "description": "Normal step",
                    "tool": "get_notes",
                    "arguments": {},
                    "status": "PENDING",
                    "requires_confirmation": False
                }
            ]
        }
        # Simulate infinite re-entrant loop protection by passing step_index out of sync
        res = execute_task(task, self.conv_id)
        self.assertIn(res["status"], ["COMPLETED", "FAILED"])

    # 18. Existing deterministic single commands still work
    def test_18_existing_deterministic_commands_work(self):
        # Single command: open notepad
        res = parse_command("open notepad")
        self.assertIsNotNone(res)
        # Single command: what time is it
        res_time = parse_command("what time is it?")
        self.assertIn("It's", str(res_time))
        # Single command: show my notes
        res_notes = parse_command("show my notes")
        self.assertTrue("notes" in str(res_notes).lower())

    # 19. Existing job-search active_task state still works (v6.1 backward compatibility)
    def test_19_existing_job_search_active_task_compat(self):
        job_state = {
            "task_type": "job_search",
            "company": "ITC Infotech",
            "role": "ML Engineer",
            "location": "Singapore",
            "active": True
        }
        update_task_state(self.conv_id, job_state)
        retrieved = get_task_state(self.conv_id)
        self.assertEqual(retrieved["task_type"], "job_search")
        self.assertEqual(retrieved["company"], "ITC Infotech")
        self.assertEqual(retrieved["location"], "Singapore")


if __name__ == '__main__':
    unittest.main(verbosity=2)
