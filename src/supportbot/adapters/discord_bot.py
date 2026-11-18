"""Discord adapter: discord.py 2. Members mention the bot or use the /ask slash command."""

from __future__ import annotations

import asyncio
import contextlib

import discord
from discord import app_commands

from supportbot.brain import ChatKind, DeleteMessage, Message, NotifyModerators, Reply, SupportBrain
from supportbot.guardrails.leaks import find_leaks
from supportbot.settings import Settings


def to_message(event: discord.Message, *, bot_id: int, admins: frozenset[str]) -> Message | None:
    if event.author.bot or not event.content:
        return None
    private = event.guild is None
    mentioned = any(user.id == bot_id for user in event.mentions)
    text = event.content.replace(f"<@{bot_id}>", "").replace(f"<@!{bot_id}>", "").strip()
    return Message(
        platform="discord",
        chat_id=str(event.channel.id),
        user_id=str(event.author.id),
        user_name=event.author.display_name,
        text=text,
        chat_kind=ChatKind.DIRECT if private else ChatKind.GROUP,
        addressed=private or mentioned,
        is_admin=f"discord:{event.author.id}" in admins,
    )


def build_client(brain: SupportBrain, settings: Settings) -> discord.Client:
    intents = discord.Intents.default()
    # Privileged intent: switch on "Message Content Intent" for the bot in the developer
    # portal. Without it Discord delivers empty text and the leak detector sees nothing.
    intents.message_content = True
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    async def notify_moderators(text: str) -> None:
        if not settings.discord_moderator_channel:
            return
        channel = client.get_channel(int(settings.discord_moderator_channel))
        if isinstance(channel, discord.abc.Messageable):
            await channel.send(text)

    @client.event
    async def on_ready() -> None:
        await tree.sync()

    @client.event
    async def on_message(event: discord.Message) -> None:
        if client.user is None:
            return
        message = to_message(event, bot_id=client.user.id, admins=settings.admins)
        if message is None:
            return
        for action in await asyncio.to_thread(brain.handle, message):
            if isinstance(action, DeleteMessage):
                # Needs "Manage Messages" in the channel, and is never possible in a DM.
                with contextlib.suppress(discord.Forbidden, discord.NotFound):
                    await event.delete()
            elif isinstance(action, Reply):
                await event.channel.send(action.text)
            elif isinstance(action, NotifyModerators):
                await notify_moderators(action.text)

    @tree.command(name="ask", description="Ask a question about the project")
    @app_commands.describe(question="Your question")
    async def ask(interaction: discord.Interaction, question: str) -> None:
        message = Message(
            platform="discord",
            chat_id=str(interaction.channel_id),
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
            text=f"/ask {question}",
            chat_kind=ChatKind.GROUP if interaction.guild_id else ChatKind.DIRECT,
            is_admin=f"discord:{interaction.user.id}" in settings.admins,
        )
        # A slash command cannot be deleted afterwards, so when it carries a secret the
        # whole exchange is made visible to its author only.
        await interaction.response.defer(thinking=True, ephemeral=bool(find_leaks(question)))
        actions = await asyncio.to_thread(brain.handle, message)
        replies = [action.text for action in actions if isinstance(action, Reply)]
        await interaction.followup.send("\n\n".join(replies) or "Done.")
        for action in actions:
            if isinstance(action, NotifyModerators):
                await notify_moderators(action.text)

    return client


async def run(brain: SupportBrain, settings: Settings) -> None:
    await build_client(brain, settings).start(settings.discord_token)
