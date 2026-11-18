"""Settings from environment variables. The CLI loads a local ``.env`` file first."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from supportbot.answer import KnowledgeBaseBackend, RagApiBackend
from supportbot.brain import DEFAULT_SAFETY_NOTICE, SupportBrain
from supportbot.guardrails.ratelimit import RateLimiter
from supportbot.kb import Retriever, load_knowledge_base
from supportbot.kb.retriever import DEFAULT_MIN_CONFIDENCE
from supportbot.storage import Store

_ADMIN_RE = re.compile(r"(telegram|discord):\d+")


class SettingsError(Exception):
    """A setting is missing or invalid. The message names the variable and the fix."""


@dataclass(frozen=True, slots=True)
class Settings:
    kb_dir: Path = Path("sample_kb")
    db_path: Path = Path("supportbot.sqlite3")
    backend: str = "kb"
    rag_api_url: str = "http://127.0.0.1:8000"
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    admins: frozenset[str] = frozenset()
    hash_salt: str = ""
    safety_notice: str = DEFAULT_SAFETY_NOTICE
    store_unanswered: bool = True
    rate_burst: int = 3
    rate_refill_seconds: float = 20.0
    telegram_token: str = ""
    telegram_moderator_chat: str = ""
    discord_token: str = ""
    discord_moderator_channel: str = ""


def _number(env: Mapping[str, str], name: str, default: float, minimum: float) -> float:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        raise SettingsError(f"{name} must be a number, not '{raw}'.") from None
    if value < minimum:
        raise SettingsError(f"{name} must be at least {minimum:g}, not {raw}.")
    return value


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    defaults = Settings()

    backend = env.get("SUPPORTBOT_BACKEND", defaults.backend)
    if backend not in ("kb", "rag-api"):
        raise SettingsError(f"SUPPORTBOT_BACKEND must be 'kb' or 'rag-api', not '{backend}'.")
    admins = frozenset(
        entry.strip() for entry in env.get("SUPPORTBOT_ADMINS", "").split(",") if entry.strip()
    )
    for admin in admins:
        if not _ADMIN_RE.fullmatch(admin):
            raise SettingsError(
                f"SUPPORTBOT_ADMINS entry '{admin}' is not valid. Use platform:user_id, "
                "for example telegram:123456789,discord:987654321."
            )
    min_confidence = _number(env, "SUPPORTBOT_MIN_CONFIDENCE", defaults.min_confidence, 0.0)
    if min_confidence > 1.0:
        raise SettingsError("SUPPORTBOT_MIN_CONFIDENCE must be between 0 and 1.")

    return Settings(
        kb_dir=Path(env.get("SUPPORTBOT_KB_DIR", str(defaults.kb_dir))),
        db_path=Path(env.get("SUPPORTBOT_DB", str(defaults.db_path))),
        backend=backend,
        rag_api_url=env.get("SUPPORTBOT_RAG_API_URL", defaults.rag_api_url),
        min_confidence=min_confidence,
        admins=admins,
        hash_salt=env.get("SUPPORTBOT_HASH_SALT", ""),
        safety_notice=env.get("SUPPORTBOT_SAFETY_NOTICE", defaults.safety_notice),
        store_unanswered=env.get("SUPPORTBOT_STORE_UNANSWERED", "true").lower() != "false",
        rate_burst=int(_number(env, "SUPPORTBOT_RATE_BURST", defaults.rate_burst, 1)),
        rate_refill_seconds=_number(
            env, "SUPPORTBOT_RATE_REFILL_SECONDS", defaults.rate_refill_seconds, 0.1
        ),
        telegram_token=env.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_moderator_chat=env.get("TELEGRAM_MODERATOR_CHAT_ID", ""),
        discord_token=env.get("DISCORD_BOT_TOKEN", ""),
        discord_moderator_channel=env.get("DISCORD_MODERATOR_CHANNEL_ID", ""),
    )


def build_brain(
    settings: Settings, store: Store, limiter: RateLimiter | None = None
) -> SupportBrain:
    if settings.backend == "rag-api":
        backend = RagApiBackend(settings.rag_api_url)
    else:
        retriever = Retriever(load_knowledge_base(settings.kb_dir))
        backend = KnowledgeBaseBackend(retriever, settings.min_confidence)
    limiter = limiter or RateLimiter(settings.rate_burst, settings.rate_refill_seconds)
    return SupportBrain(backend, store, limiter, safety_notice=settings.safety_notice)
