"""Command-line entry point: `supportbot <command>`."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from supportbot import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="supportbot",
        description="Support bot for Telegram and Discord communities.",
    )
    parser.add_argument("--version", action="version", version=f"supportbot {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
