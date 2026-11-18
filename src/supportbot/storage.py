"""Tickets and analytics in SQLite.

Analytics rows identify a member only by a salted hash, and keep the question text
only for questions the bot could not answer. Tickets keep the display name and the
chat, because a moderator has to find the person to answer them.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from supportbot.guardrails.leaks import redact
from supportbot.kb.text import normalize_question

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    platform TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    member TEXT NOT NULL,
    question TEXT NOT NULL,
    resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    platform TEXT NOT NULL,
    member_hash TEXT NOT NULL,
    outcome TEXT NOT NULL,
    source TEXT,
    confidence REAL,
    question TEXT
);
"""
OUTCOMES = ("answered", "handoff", "refused", "blocked", "rate_limited")


@dataclass(frozen=True, slots=True)
class Ticket:
    id: int
    platform: str
    chat_id: str
    member: str
    question: str


@dataclass(frozen=True, slots=True)
class Summary:
    days: int
    outcomes: dict[str, int]
    unanswered: list[tuple[str, int]]  # normalized question, times asked
    sources: list[tuple[str, int]]  # knowledge base section, times used

    @property
    def answer_rate(self) -> float | None:
        answered = self.outcomes.get("answered", 0)
        asked = answered + self.outcomes.get("handoff", 0)
        return answered / asked if asked else None


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(
        self,
        path: str | Path,
        *,
        salt: str,
        store_unanswered: bool = True,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        # The brain serializes access with its own lock, so one connection is shared by the
        # worker threads the adapters run it on.
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._salt = salt
        self._store_unanswered = store_unanswered
        self._clock = clock

    def close(self) -> None:
        self._db.close()

    def open_ticket(self, platform: str, chat_id: str, member: str, question: str) -> int:
        with self._db:
            cursor = self._db.execute(
                "INSERT INTO tickets (created_at, platform, chat_id, member, question) "
                "VALUES (?, ?, ?, ?, ?)",
                (self._clock().isoformat(), platform, chat_id, member, redact(question)),
            )
        return int(cursor.lastrowid or 0)

    def open_tickets(self, limit: int = 10) -> list[Ticket]:
        rows = self._db.execute(
            "SELECT id, platform, chat_id, member, question FROM tickets "
            "WHERE resolved_at IS NULL ORDER BY id LIMIT ?",
            (limit,),
        )
        return [Ticket(*row) for row in rows]

    def resolve(self, ticket_id: int) -> bool:
        with self._db:
            cursor = self._db.execute(
                "UPDATE tickets SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL",
                (self._clock().isoformat(), ticket_id),
            )
        return cursor.rowcount == 1

    def record(
        self,
        platform: str,
        user_id: str,
        outcome: str,
        *,
        source: str | None = None,
        confidence: float | None = None,
        question: str | None = None,
    ) -> None:
        member = hashlib.sha256(f"{self._salt}:{platform}:{user_id}".encode()).hexdigest()[:16]
        keep_question = question and outcome == "handoff" and self._store_unanswered
        with self._db:
            self._db.execute(
                "INSERT INTO events (at, platform, member_hash, outcome, source, confidence, "
                "question) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    self._clock().isoformat(),
                    platform,
                    member,
                    outcome,
                    source,
                    confidence,
                    redact(question) if keep_question else None,
                ),
            )

    def summary(self, days: int = 7) -> Summary:
        since = (self._clock() - timedelta(days=days)).isoformat()
        outcomes = dict(
            self._db.execute(
                "SELECT outcome, COUNT(*) FROM events WHERE at >= ? GROUP BY outcome", (since,)
            )
        )
        questions = self._db.execute(
            "SELECT question FROM events "
            "WHERE at >= ? AND outcome = 'handoff' AND question IS NOT NULL",
            (since,),
        )
        # Grouping by normalized text merges "When is the listing?" with "when is the listing".
        unanswered = Counter(normalize_question(question) for (question,) in questions)
        sources = self._db.execute(
            "SELECT source, COUNT(*) AS uses FROM events "
            "WHERE at >= ? AND outcome = 'answered' AND source IS NOT NULL "
            "GROUP BY source ORDER BY uses DESC, source LIMIT 5",
            (since,),
        )
        return Summary(days, outcomes, unanswered.most_common(5), [tuple(row) for row in sources])


def format_summary(summary: Summary) -> str:
    counts = {outcome: summary.outcomes.get(outcome, 0) for outcome in OUTCOMES}
    rate = summary.answer_rate
    answered = f"{counts['answered']} answered"
    if rate is not None:
        answered += f" ({rate:.0%})"
    lines = [
        f"Last {summary.days} days: {answered}, {counts['handoff']} handed off, "
        f"{counts['refused']} refused, {counts['blocked']} leaks removed, "
        f"{counts['rate_limited']} rate-limited"
    ]
    if summary.unanswered:
        lines.append("Unanswered most often (documentation to write next):")
        lines.extend(f"  {count}x {question}" for question, count in summary.unanswered)
    if summary.sources:
        lines.append("Most used sections:")
        lines.extend(f"  {count}x {source}" for source, count in summary.sources)
    return "\n".join(lines)
