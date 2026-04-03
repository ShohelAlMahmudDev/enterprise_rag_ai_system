import logging
import sqlite3
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(self) -> None:
        self.db_path = self._resolve_db_path()
        self._initialize()

    def _resolve_db_path(self) -> str:
        db_url = settings.DATABASE_URL

        if db_url.startswith("sqlite:///"):
            return db_url.replace("sqlite:///", "", 1)

        return "./data/app.db"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_memory_session_id
                ON chat_memory (session_id)
                """
            )
            conn.commit()

        logger.info("SQLite memory service initialized at %s", self.db_path)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        if not session_id or not content or not content.strip():
            return

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_memory (session_id, role, content)
                VALUES (?, ?, ?)
                """,
                (session_id, role, content.strip()),
            )
            conn.commit()

        logger.info("Memory add | session=%s | role=%s", session_id, role)

    def get_recent_messages(self, session_id: str, limit: int = 6) -> list[dict]:
        if not session_id:
            return []

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at
                FROM chat_memory
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        messages = [
            {
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in reversed(rows)
        ]

        logger.info("Memory get recent | session=%s | count=%s", session_id, len(messages))
        return messages

    def get_full_history(self, session_id: str) -> list[dict]:
        if not session_id:
            return []

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content, created_at
                FROM chat_memory
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()

        history = [
            {
                "id": str(row["id"]),
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

        logger.info("Memory get full history | session=%s | count=%s", session_id, len(history))
        return history

    def clear_session(self, session_id: str) -> None:
        if not session_id:
            return

        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM chat_memory
                WHERE session_id = ?
                """,
                (session_id,),
            )
            conn.commit()

        logger.info("Memory cleared | session=%s", session_id)

    def trim_session(self, session_id: str, keep_last: int = 20) -> None:
        if not session_id or keep_last <= 0:
            return

        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM chat_memory
                WHERE session_id = ?
                  AND id NOT IN (
                      SELECT id
                      FROM chat_memory
                      WHERE session_id = ?
                      ORDER BY id DESC
                      LIMIT ?
                  )
                """,
                (session_id, session_id, keep_last),
            )
            conn.commit()

        logger.info("Memory trimmed | session=%s | keep_last=%s", session_id, keep_last)