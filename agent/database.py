import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'spidy_memory.db')

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS conversations (
                            id TEXT PRIMARY KEY,
                            created_at TEXT,
                            updated_at TEXT,
                            title TEXT,
                            active_task TEXT,
                            pending_clarification TEXT
                          )''')
        try:
            cursor.execute("ALTER TABLE conversations ADD COLUMN pending_clarification TEXT")
        except Exception:
            pass
        cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            conversation_id TEXT,
                            role TEXT,
                            content TEXT,
                            timestamp TEXT,
                            is_tool_result BOOLEAN DEFAULT 0
                          )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS memory (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            key TEXT UNIQUE,
                            value TEXT,
                            importance INTEGER DEFAULT 1,
                            created_at TEXT,
                            updated_at TEXT
                          )''')
        conn.commit()

init_db()

def create_conversation(conv_id, title="New Conversation"):
    with get_connection() as conn:
        now = datetime.now().isoformat()
        conn.execute("INSERT OR IGNORE INTO conversations (id, created_at, updated_at, title) VALUES (?, ?, ?, ?)",
                     (conv_id, now, now, title))
        conn.commit()

def add_message(conv_id, role, content, is_tool=False):
    with get_connection() as conn:
        now = datetime.now().isoformat()
        conn.execute("INSERT INTO messages (conversation_id, role, content, timestamp, is_tool_result) VALUES (?, ?, ?, ?, ?)",
                     (conv_id, role, content, now, is_tool))
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
        conn.commit()

def get_recent_messages(conv_id, limit=12):
    with get_connection() as conn:
        cursor = conn.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?", (conv_id, limit))
        rows = cursor.fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

def set_long_term_memory(key, value, importance=1):
    with get_connection() as conn:
        now = datetime.now().isoformat()
        conn.execute('''INSERT INTO memory (key, value, importance, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, importance=excluded.importance''',
                     (key, value, importance, now, now))
        conn.commit()

def get_all_long_term_memory():
    with get_connection() as conn:
        cursor = conn.execute("SELECT key, value FROM memory ORDER BY importance DESC")
        return {r[0]: r[1] for r in cursor.fetchall()}

def clear_conversation(conv_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        conn.execute("UPDATE conversations SET active_task = NULL, pending_clarification = NULL WHERE id = ?", (conv_id,))
        conn.commit()

def update_task_state(conv_id, task_state):
    with get_connection() as conn:
        conn.execute("UPDATE conversations SET active_task = ? WHERE id = ?", (json.dumps(task_state) if task_state else None, conv_id))
        conn.commit()

def get_task_state(conv_id):
    with get_connection() as conn:
        cursor = conn.execute("SELECT active_task FROM conversations WHERE id = ?", (conv_id,))
        row = cursor.fetchone()
        if row and row[0]:
            return json.loads(row[0])
        return None

def set_pending_clarification(conv_id, clarification_dict):
    with get_connection() as conn:
        now = datetime.now().isoformat()
        val = json.dumps(clarification_dict) if clarification_dict else None
        res = conn.execute("UPDATE conversations SET pending_clarification = ?, updated_at = ? WHERE id = ?", (val, now, conv_id))
        if res.rowcount == 0:
            conn.execute("INSERT OR IGNORE INTO conversations (id, created_at, updated_at, title, pending_clarification) VALUES (?, ?, ?, ?, ?)",
                         (conv_id, now, now, "Session", val))
        conn.commit()

def get_pending_clarification(conv_id):
    with get_connection() as conn:
        cursor = conn.execute("SELECT pending_clarification FROM conversations WHERE id = ?", (conv_id,))
        row = cursor.fetchone()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except Exception:
                return None
        return None

def clear_pending_clarification(conv_id):
    with get_connection() as conn:
        conn.execute("UPDATE conversations SET pending_clarification = NULL WHERE id = ?", (conv_id,))
        conn.commit()

