import sqlite3
import os
import json
from datetime import datetime

DB_PATH = "data/data.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# === Initialization ===
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY
            )
        """)
        conn.commit()

def init_state_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )''')
        conn.commit()

# === Subscriber Logic ===
def add_subscriber(chat_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO subscribers (chat_id) VALUES (?)", (chat_id,))
        conn.commit()

def remove_subscriber(chat_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        conn.commit()

def get_all_subscribers():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM subscribers")
        return {row[0] for row in cursor.fetchall()}

# === State Logic ===
def default_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)

def try_parse_datetime(obj):
    # Try to decode a list of 2 datetime strings into a tuple of datetime
    if isinstance(obj, list) and len(obj) == 2:
        try:
            return tuple(datetime.fromisoformat(x) for x in obj)
        except Exception:
            pass
    return obj

def get_state(key):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM state WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            value = json.loads(row[0])
            return try_parse_datetime(value)
        return None

def set_state(key, value):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("REPLACE INTO state (key, value) VALUES (?, ?)", (key, json.dumps(value, default=default_serializer)))
        conn.commit()
