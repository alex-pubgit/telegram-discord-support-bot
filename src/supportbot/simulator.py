"""Chat with the bot in a terminal, with no Telegram or Discord account.

Each input line is one chat message:

    alice: @bot How much is the bridge fee?      a member, in the group, talking to the bot
    bob: gm everyone                             a member, in the group, not talking to the bot
    mia (mod): /tickets                          a moderator
    dan (dm): hello                              a direct message

Lines that are empty or start with ``#`` are skipped. The transcript never repeats a
detected secret: the member's line is shown the way the chat looks after the bot acted.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

from supportbot.brain import (
    ChatKind,
    DeleteMessage,
    Message,
    NotifyModerators,
    Reply,
    SupportBrain,
)
from supportbot.guardrails.leaks import redact

_LINE_RE = re.compile(r"^(?P<name>\w+)(?:\s*\((?P<role>mod|dm)\))?:\s?(?P<text>.*)$")
_MENTION_RE = re.compile(r"@bot\b[,:]?\s*", re.IGNORECASE)


class ScriptError(Exception):
    """A simulator line could not be understood."""


def parse_line(line: str) -> Message:
    match = _LINE_RE.match(line.strip())
    if not match:
        raise ScriptError(f"Cannot read this line: {line!r}. Expected 'name: message'.")
    text = match["text"]
    direct = match["role"] == "dm"
    return Message(
        platform="simulator",
        chat_id="dm" if direct else "group",
        user_id=match["name"].lower(),
        user_name=match["name"],
        text=_MENTION_RE.sub("", text).strip(),
        chat_kind=ChatKind.DIRECT if direct else ChatKind.GROUP,
        addressed=direct or text.startswith("/") or bool(_MENTION_RE.search(text)),
        is_admin=match["role"] == "mod",
    )


def _indented(prefix: str, text: str) -> Iterator[str]:
    first, *rest = text.split("\n")
    yield f"{prefix}{first}"
    yield from (" " * len(prefix) + line if line else "" for line in rest)


def run_script(lines: Iterable[str], brain: SupportBrain) -> Iterator[str]:
    """Feed each line to the brain and yield the transcript, line by line."""
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        message = parse_line(line)
        actions = brain.handle(message)
        shown = line.strip()
        if any(isinstance(action, DeleteMessage) for action in actions):
            shown = redact(shown)
        yield shown
        for action in actions:
            if isinstance(action, DeleteMessage):
                yield "  (bot deleted this message)"
            elif isinstance(action, Reply):
                yield from _indented("  bot: ", action.text)
            elif isinstance(action, NotifyModerators):
                yield from _indented("  bot -> moderators: ", action.text)
