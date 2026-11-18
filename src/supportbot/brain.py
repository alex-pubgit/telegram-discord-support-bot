"""The transport-agnostic core: one incoming message in, a list of actions out.

Nothing in this module knows about Telegram or Discord. An adapter turns a platform
event into a `Message`, calls `SupportBrain.handle`, and executes the actions it gets
back. That keeps every rule below testable without a network.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import StrEnum

from supportbot.answer import AnswerBackend, BackendError
from supportbot.guardrails.leaks import LeakKind, find_leaks
from supportbot.guardrails.ratelimit import RateLimiter
from supportbot.guardrails.topics import asks_for_financial_advice, needs_safety_notice
from supportbot.storage import Store, format_summary

logger = logging.getLogger(__name__)

DEFAULT_SAFETY_NOTICE = (
    "Safety reminder: admins never message you first and never ask for your seed phrase "
    "or private key. There is no wallet validation or sync tool."
)
ADVICE_REFUSAL = (
    "I can't give price predictions or investment advice. "
    "I'm happy to explain how the product works."
)
HELP = (
    "Ask me about the project and I'll answer from the official documentation.\n"
    "/ask <question> - ask in a group\n"
    "/human <question> - send your question to the team"
)
MODERATOR_COMMANDS = frozenset({"/tickets", "/resolve", "/stats"})
MEMBER_COMMANDS = frozenset({"", "/ask", "/human"})
_SECRET_NAMES = {
    LeakKind.SEED_PHRASE: "wallet recovery phrase",
    LeakKind.PRIVATE_KEY: "private key",
}


class ChatKind(StrEnum):
    DIRECT = "direct"
    GROUP = "group"


@dataclass(frozen=True, slots=True)
class Message:
    platform: str
    chat_id: str
    user_id: str
    user_name: str
    text: str
    chat_kind: ChatKind = ChatKind.DIRECT
    # In a group: the bot was mentioned, replied to, or sent a command.
    addressed: bool = True
    is_admin: bool = False


@dataclass(frozen=True, slots=True)
class Reply:
    text: str


@dataclass(frozen=True, slots=True)
class DeleteMessage:
    """Remove the message that is being handled."""


@dataclass(frozen=True, slots=True)
class NotifyModerators:
    text: str


Action = Reply | DeleteMessage | NotifyModerators


class SupportBrain:
    def __init__(
        self,
        backend: AnswerBackend,
        store: Store,
        limiter: RateLimiter,
        *,
        safety_notice: str = DEFAULT_SAFETY_NOTICE,
    ) -> None:
        self._backend = backend
        self._store = store
        self._limiter = limiter
        self._safety_notice = safety_notice
        # Adapters call handle() from worker threads. One message at a time keeps the rate
        # limiter and the SQLite connection consistent.
        self._lock = threading.Lock()

    def handle(self, message: Message) -> list[Action]:
        with self._lock:
            return self._handle(message)

    def _handle(self, message: Message) -> list[Action]:
        # Leaks come first and apply to every message, whether or not it is meant for the bot.
        leaks = find_leaks(message.text)
        if leaks:
            self._store.record(message.platform, message.user_id, "blocked")
            secret = _SECRET_NAMES[leaks[0].kind]
            warning = (
                f"{message.user_name}, I removed your message because it looked like a {secret}. "
                "If it was one, treat that wallet as compromised and move your funds to a "
                "new wallet now. Nobody on the team will ever ask for it."
            )
            return [DeleteMessage(), Reply(warning)]
        if message.chat_kind is ChatKind.GROUP and not message.addressed:
            return []

        if not message.is_admin:
            decision = self._limiter.check(f"{message.platform}:{message.user_id}")
            if not decision.allowed:
                self._store.record(message.platform, message.user_id, "rate_limited")
                if not decision.notify:
                    return []
                wait = decision.retry_after_seconds
                return [Reply(f"You're sending messages quickly. Please wait {wait} seconds.")]

        text = message.text.strip()
        command, question = "", text
        if text.startswith("/"):
            # Telegram sends "/ask@BotName question" in groups with several bots.
            head, _, question = text.partition(" ")
            command = head.split("@", 1)[0].lower()
            question = question.strip()

        if command in MODERATOR_COMMANDS:
            if not message.is_admin:
                return [Reply("Only moderators can use that command.")]
            return [Reply(self._moderate(command, question))]
        if command == "/human":
            return self._hand_off(message, question or "Asked to talk to the team.")
        if command not in MEMBER_COMMANDS or not question:
            return [Reply(HELP)]

        if asks_for_financial_advice(question):
            self._store.record(message.platform, message.user_id, "refused")
            return [Reply(ADVICE_REFUSAL)]

        try:
            answer = self._backend.answer(question)
        except BackendError as exc:
            # An outage of the answer service must not leave the member without help.
            logger.warning("Answer backend failed, handing off instead: %s", exc)
            answer = None
        if answer is None:
            return self._hand_off(message, question)
        self._store.record(
            message.platform,
            message.user_id,
            "answered",
            source=answer.source,
            confidence=answer.confidence,
        )
        return [Reply(self._with_notice(f"{answer.text}\n\nSource: {answer.source}", question))]

    def _hand_off(self, message: Message, question: str) -> list[Action]:
        ticket = self._store.open_ticket(
            message.platform, message.chat_id, message.user_name, question
        )
        self._store.record(message.platform, message.user_id, "handoff", question=question)
        reply = (
            "I don't have a reliable answer for that, so I passed it to the team "
            f"(ticket #{ticket}). A moderator will reply here."
        )
        notice = f"Ticket #{ticket} from {message.user_name} on {message.platform}: {question}"
        return [Reply(self._with_notice(reply, question)), NotifyModerators(notice)]

    def _with_notice(self, reply: str, question: str) -> str:
        if needs_safety_notice(question):
            return f"{reply}\n\n{self._safety_notice}"
        return reply

    def _moderate(self, command: str, argument: str) -> str:
        if command == "/tickets":
            tickets = self._store.open_tickets()
            if not tickets:
                return "No open tickets."
            return "\n".join(
                f"#{ticket.id} {ticket.member} ({ticket.platform}): {ticket.question[:200]}"
                for ticket in tickets
            )
        if command == "/resolve":
            if not argument.isdigit():
                return "Usage: /resolve <ticket number>"
            if self._store.resolve(int(argument)):
                return f"Ticket #{argument} resolved."
            return f"No open ticket #{argument}."
        return format_summary(self._store.summary(days=7))
