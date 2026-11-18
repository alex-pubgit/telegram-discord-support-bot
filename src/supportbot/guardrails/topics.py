"""Recognize two kinds of question that need special handling.

* Questions about wallet access, recovery, contacting "support", airdrops or
  "validation" tools are where impersonators strike, so every reply to them carries
  the standing scam-safety notice.
* Questions that ask for a price prediction or an investment decision get a fixed
  refusal. The bot never answers them, whatever the knowledge base says.

Both checks are plain pattern lists on purpose: they must behave the same with every
answer backend, including when no language model is configured.
"""

from __future__ import annotations

import re

_SAFETY_PATTERNS = (
    # wallet access and secrets
    r"\b(?:seed|recovery|secret|backup)\s+(?:phrase|words?)\b",
    r"\b(?:my|your|the)\s+seed\b",
    r"\bmnemonic\b",
    r"\bprivate\s*keys?\b",
    r"\b(?:access|unlock|log\s*in(?:to)?|sign\s*in(?:to)?|connect)\b.{0,30}\bwallet\b",
    r"\bwallet\b.{0,30}\b(?:access|locked|hacked|drained|compromised|stolen|empty|emptied)\b",
    # recovery
    r"\b(?:recover\w*|restor\w+|reset\w*|lost|forgot\w*)\b",
    r"\b(?:hack\w*|scam\w*|phish\w*|stolen|drain\w*)\b",
    # contacting "support"
    r"\b(?:admins?|moderators?|mods?|helpdesk|help\s+desk)\b",
    r"\bsupport\s+(?:team|agents?|staff|tickets?|chat|channel|desk|person|guy|rep)\b",
    r"\b(?:official|customer|live|tech(?:nical)?)\s+support\b",
    r"\b(?:contact|reach|call|email|talk\s+to|speak\s+to|speak\s+with|write\s+to)\b.{0,30}"
    r"\b(?:support|team|someone|somebody|agent|human)\b",
    r"\b(?:dm|dms|dmed|pm|pmed|direct\s+messages?|private\s+messages?|inbox)\b",
    # airdrops and giveaways
    r"\b(?:airdrops?|giveaways?|free\s+tokens?|claim\w*)\b",
    # "validation" tools
    r"\b(?:validat\w+|synchroni[sz]\w+|sync\w*|rectif\w+)\b",
    r"\bverif\w+\b.{0,30}\bwallet\b|\bwallet\b.{0,30}\bverif\w+\b",
)

_PRICE_MOVES = (
    r"(?:go(?:es|ing)?\s+(?:up|down)|rise|rising|fall|falling|drop|dropping|crash|crashing"
    r"|increase|decrease|recover)"
)

_ADVICE_PATTERNS = (
    r"\bprice\s+(?:prediction|target|forecast)s?\b",
    r"\bpredict\w*\b.{0,30}\bprice\b",
    r"\b(?:financial|investment|trading)\s+advice\b",
    r"\bshould\s+(?:i|we)\b.{0,20}\b(?:buy|sell|hold|invest|ape)\b",
    r"\b(?:good|great|best|right|bad)\s+(?:time|moment)\s+to\s+(?:buy|sell|invest|get\s+in)\b",
    r"\b(?:good|great|safe|solid|bad)\s+(?:investment|buy)\b",
    r"\bworth\s+(?:buying|investing|holding)\b",
    r"\b(?:will|gonna|going\s+to|can|could)\b.{0,40}"
    r"(?:\b(?:go(?:es|ing)?\s+(?:up|down)|moon|pump|dump|skyrocket)\b|\b\d+\s*x\b)",
    rf"\bprice\b.{{0,40}}\b{_PRICE_MOVES}\b",
    r"\b(?:when|wen)\s+(?:moon|lambo|pump)\b",
    r"\bhow\s+(?:high|far)\b.{0,40}\b(?:go|reach|climb)\b",
    r"\bhow\s+much\b.{0,40}\bbe\s+worth\b",
    r"\bprice\b.{0,30}\b(?:next|in)\s+(?:week|month|year|\d{4})\b",
    r"\b(?:make|get)\s+(?:me\s+)?(?:money|rich|profit)\b",
)

_SAFETY_RE = re.compile("|".join(_SAFETY_PATTERNS), re.IGNORECASE)
_ADVICE_RE = re.compile("|".join(_ADVICE_PATTERNS), re.IGNORECASE)


def needs_safety_notice(text: str) -> bool:
    """True when the message is about a topic that scammers exploit."""
    return _SAFETY_RE.search(text) is not None


def asks_for_financial_advice(text: str) -> bool:
    """True when the message asks for a price prediction or an investment decision."""
    return _ADVICE_RE.search(text) is not None
