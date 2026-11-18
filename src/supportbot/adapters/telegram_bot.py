"""Telegram adapter: aiogram 3, long polling."""

from __future__ import annotations

import asyncio
import contextlib
import re

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message as TelegramMessage

from supportbot.brain import ChatKind, DeleteMessage, Message, NotifyModerators, Reply, SupportBrain
from supportbot.settings import Settings


def to_message(
    update: TelegramMessage, *, bot_id: int, bot_username: str, admins: frozenset[str]
) -> Message | None:
    sender = update.from_user
    if not update.text or sender is None or sender.is_bot:
        return None
    private = update.chat.type == "private"
    mention = re.compile(re.escape(f"@{bot_username}"), re.IGNORECASE)
    replied_to = update.reply_to_message.from_user if update.reply_to_message else None
    addressed = (
        private
        or update.text.startswith("/")
        or bool(mention.search(update.text))
        or (replied_to is not None and replied_to.id == bot_id)
    )
    return Message(
        platform="telegram",
        chat_id=str(update.chat.id),
        user_id=str(sender.id),
        user_name=sender.full_name,
        text=mention.sub("", update.text).strip(),
        chat_kind=ChatKind.DIRECT if private else ChatKind.GROUP,
        addressed=addressed,
        is_admin=f"telegram:{sender.id}" in admins,
    )


def build_dispatcher(
    brain: SupportBrain, settings: Settings, bot: Bot, *, bot_id: int, bot_username: str
) -> Dispatcher:
    dispatcher = Dispatcher()

    @dispatcher.message(F.text)
    async def on_text(update: TelegramMessage) -> None:
        message = to_message(
            update, bot_id=bot_id, bot_username=bot_username, admins=settings.admins
        )
        if message is None:
            return
        # The brain may wait on an answer service, so it runs off the event loop.
        for action in await asyncio.to_thread(brain.handle, message):
            if isinstance(action, DeleteMessage):
                # Needs the "Delete messages" admin right. Without it the warning still goes out.
                with contextlib.suppress(TelegramAPIError):
                    await update.delete()
            elif isinstance(action, Reply):
                await update.answer(action.text)
            elif isinstance(action, NotifyModerators) and settings.telegram_moderator_chat:
                await bot.send_message(settings.telegram_moderator_chat, action.text)

    return dispatcher


async def run(brain: SupportBrain, settings: Settings) -> None:
    bot = Bot(settings.telegram_token)
    me = await bot.get_me()
    dispatcher = build_dispatcher(
        brain, settings, bot, bot_id=me.id, bot_username=me.username or ""
    )
    await dispatcher.start_polling(bot)
