"""Command-line entry point: `supportbot <command>`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from supportbot import __version__
from supportbot.guardrails.ratelimit import RateLimiter
from supportbot.kb import KnowledgeBaseError
from supportbot.settings import SettingsError, build_brain, load_settings
from supportbot.simulator import ScriptError, run_script
from supportbot.storage import Store, format_summary


def _simulate(args: argparse.Namespace) -> int:
    settings = load_settings()
    if args.kb:
        settings = replace(settings, kb_dir=Path(args.kb))
    store = Store(":memory:", salt="simulator")
    # A script sends many messages at once, so the simulator does not rate-limit them.
    brain = build_brain(settings, store, RateLimiter(burst=1000, refill_seconds=1.0))
    if args.script:
        # utf-8-sig: Windows editors often save a byte-order mark in front of the first line.
        lines = Path(args.script).read_text(encoding="utf-8-sig").splitlines()
    else:
        print("Type 'name: message' (see `supportbot simulate --help`). Ctrl+D or Ctrl+Z ends.")
        lines = sys.stdin
    for line in run_script(lines, brain):
        print(line)
    return 0


def _report(args: argparse.Namespace) -> int:
    path = Path(args.db) if args.db else load_settings().db_path
    if not path.is_file():
        raise SettingsError(f"No database at '{path}'. Run the bot first, or pass --db.")
    store = Store(path, salt="")
    print(format_summary(store.summary(args.days)))
    store.close()
    return 0


def _run(args: argparse.Namespace) -> int:
    settings = load_settings()
    token = settings.telegram_token if args.platform == "telegram" else settings.discord_token
    if not token:
        raise SettingsError(
            f"Set {args.platform.upper()}_BOT_TOKEN to run the {args.platform} bot."
        )
    if not settings.hash_salt:
        raise SettingsError(
            "Set SUPPORTBOT_HASH_SALT to any long random string. "
            "It keeps member ids in the analytics table pseudonymous."
        )
    try:
        if args.platform == "telegram":
            from supportbot.adapters import telegram_bot as adapter
        else:
            from supportbot.adapters import discord_bot as adapter
    except ImportError as exc:
        raise SettingsError(
            f"The {args.platform} adapter is not installed. "
            f'Run: pip install "supportbot[{args.platform}]"'
        ) from exc
    store = Store(
        settings.db_path, salt=settings.hash_salt, store_unanswered=settings.store_unanswered
    )
    asyncio.run(adapter.run(build_brain(settings, store), settings))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="supportbot",
        description="Support bot for Telegram and Discord communities.",
    )
    parser.add_argument("--version", action="version", version=f"supportbot {__version__}")
    commands = parser.add_subparsers(metavar="command")

    simulate = commands.add_parser(
        "simulate",
        help="chat with the bot in the terminal, no accounts needed",
        description="Each line is 'name: message'. Add (mod) or (dm) after the name for a "
        "moderator or a direct message, and start a group message with @bot to address the bot.",
    )
    simulate.add_argument("--script", help="replay the lines of this file and print the transcript")
    simulate.add_argument("--kb", help="knowledge base folder (default: SUPPORTBOT_KB_DIR)")
    simulate.set_defaults(run=_simulate)

    report = commands.add_parser("report", help="what members asked and what went unanswered")
    report.add_argument("--days", type=int, default=7)
    report.add_argument("--db", help="database file (default: SUPPORTBOT_DB)")
    report.set_defaults(run=_report)

    run = commands.add_parser("run", help="start the bot on a platform")
    run.add_argument("platform", choices=("telegram", "discord"))
    run.set_defaults(run=_run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "run"):
        parser.print_help()
        return 0
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # One line per HTTP request is noise, and a Telegram request URL contains the bot token.
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    try:
        return args.run(args)
    except (SettingsError, KnowledgeBaseError, ScriptError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
