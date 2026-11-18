"""Adapter tests. They need the optional platform libraries, and no network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bip39_vectors import phrase_of_length
from supportbot.brain import ChatKind
from supportbot.settings import Settings

pytest.importorskip("aiogram")
pytest.importorskip("discord")

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage
from aiogram.types import Message as TelegramMessage

from supportbot.adapters import discord_bot, telegram_bot

BOT_ID = 4242
ADMINS = frozenset({"telegram:7", "discord:7"})


def telegram_update(text: str, *, chat_type: str = "supergroup", user_id: int = 7, **extra):
    return {
        "message_id": 11,
        "date": 1_700_000_000,
        "chat": {"id": -100123, "type": chat_type},
        "from": {"id": user_id, "is_bot": False, "first_name": "Alice", "last_name": "Lee"},
        "text": text,
        **extra,
    }


def from_telegram(text: str, **fields):
    update = TelegramMessage.model_validate(telegram_update(text, **fields))
    return telegram_bot.to_message(update, bot_id=BOT_ID, bot_username="AcmeBot", admins=ADMINS)


def test_telegram_private_chat_is_always_meant_for_the_bot():
    message = from_telegram("hello", chat_type="private")
    assert message.chat_kind is ChatKind.DIRECT
    assert message.addressed


@pytest.mark.parametrize(
    ("text", "extra", "addressed"),
    [
        ("how are fees charged?", {}, False),
        ("@acmebot how are fees charged?", {}, True),
        ("/ask how are fees charged?", {}, True),
        (
            "and the bridge?",
            {
                "reply_to_message": {
                    "message_id": 10,
                    "date": 1_700_000_000,
                    "chat": {"id": -100123, "type": "supergroup"},
                    "from": {"id": BOT_ID, "is_bot": True, "first_name": "Acme"},
                    "text": "earlier answer",
                }
            },
            True,
        ),
    ],
)
def test_telegram_group_message_is_addressed_by_mention_command_or_reply(text, extra, addressed):
    message = from_telegram(text, **extra)
    assert message.chat_kind is ChatKind.GROUP
    assert message.addressed is addressed


def test_telegram_mention_is_removed_and_identity_is_mapped():
    message = from_telegram("@AcmeBot how are fees charged?")
    assert message.text == "how are fees charged?"
    assert (message.user_id, message.user_name, message.chat_id) == ("7", "Alice Lee", "-100123")
    assert message.is_admin
    assert not from_telegram("hi", user_id=8).is_admin


class RecordingSession(BaseSession):
    """Stands in for Telegram's HTTP API and records every call the bot makes."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list = []

    async def close(self) -> None:
        pass

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, SendMessage):
            sent = telegram_update(method.text, user_id=BOT_ID)
            return TelegramMessage.model_validate(sent)
        return True

    async def stream_content(self, *args, **kwargs):
        yield b""


async def test_telegram_dispatcher_deletes_a_leak_warns_and_answers(brain):
    session = RecordingSession()
    bot = Bot("4242:TEST", session=session)
    settings = Settings(telegram_moderator_chat="-100999")
    dispatcher = telegram_bot.build_dispatcher(
        brain, settings, bot, bot_id=BOT_ID, bot_username="AcmeBot"
    )
    phrase = phrase_of_length(12)

    leak = {"update_id": 1, "message": telegram_update(f"my words: {phrase}")}
    await dispatcher.feed_raw_update(bot, leak)
    question = {"update_id": 2, "message": telegram_update("@AcmeBot when is the listing?")}
    await dispatcher.feed_raw_update(bot, question)

    kinds = [type(call).__name__ for call in session.calls]
    assert kinds == ["DeleteMessage", "SendMessage", "SendMessage", "SendMessage"]
    assert phrase not in session.calls[1].text
    assert "ticket #1" in session.calls[2].text
    assert (session.calls[3].chat_id, session.calls[3].text[:9]) == ("-100999", "Ticket #1")


def discord_event(content: str, *, guild: bool = True, mentions=(), bot: bool = False):
    return SimpleNamespace(
        author=SimpleNamespace(bot=bot, id=7, display_name="Alice"),
        content=content,
        guild=object() if guild else None,
        mentions=[SimpleNamespace(id=user_id) for user_id in mentions],
        channel=SimpleNamespace(id=555),
    )


def from_discord(content: str, **fields):
    return discord_bot.to_message(discord_event(content, **fields), bot_id=BOT_ID, admins=ADMINS)


def test_discord_mention_addresses_the_bot_and_is_removed():
    message = from_discord(f"<@{BOT_ID}> how are fees charged?", mentions=[BOT_ID])
    assert message.addressed
    assert message.text == "how are fees charged?"
    assert (message.user_id, message.chat_id, message.is_admin) == ("7", "555", True)


def test_discord_channel_message_without_a_mention_is_not_addressed():
    message = from_discord("how are fees charged?")
    assert message.chat_kind is ChatKind.GROUP
    assert not message.addressed


def test_discord_direct_message_is_always_meant_for_the_bot():
    assert from_discord("hello", guild=False).addressed


@pytest.mark.parametrize("fields", [{"bot": True}, {"content": ""}])
def test_discord_bot_authors_and_empty_content_are_ignored(fields):
    event = discord_event(fields.pop("content", "hello"), **fields)
    assert discord_bot.to_message(event, bot_id=BOT_ID, admins=ADMINS) is None


def test_discord_client_asks_for_message_content_and_registers_handlers(brain):
    client = discord_bot.build_client(brain, Settings())
    assert client.intents.message_content
    assert callable(client.on_message)
    assert callable(client.on_ready)
