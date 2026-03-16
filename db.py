import sqlite3
from datetime import datetime

from models import SavedGroup

DB_PATH = "telex.db"


class Database:
    """Per-instance database wrapper."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY,
                    title TEXT,
                    username TEXT,
                    joined_at TEXT
                )
                """
            )
            conn.commit()

    def save_group(self, chat_id: int, title: str, username: str | None):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO groups (id, title, username, joined_at) VALUES (?, ?, ?, ?)",
                (chat_id, title, username, datetime.now().isoformat()),
            )
            conn.commit()

    def get_all_groups(self) -> list[SavedGroup]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM groups
                WHERE username IS NOT NULL AND username != ''
                GROUP BY username
                HAVING id = MAX(id)
                UNION ALL
                SELECT * FROM groups
                WHERE username IS NULL OR username = ''
                ORDER BY joined_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def remove_group(self, chat_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM groups WHERE id = ?", (chat_id,))
            conn.commit()


# --- Default instance (backward compatible) ---
_default = Database(DB_PATH)


def _connect():
    return _default._connect()


def init_db():
    _default.init_db()


def save_group(chat_id: int, title: str, username: str | None):
    _default.save_group(chat_id, title, username)


def get_all_groups() -> list[SavedGroup]:
    return _default.get_all_groups()


def remove_group(chat_id: int):
    _default.remove_group(chat_id)
