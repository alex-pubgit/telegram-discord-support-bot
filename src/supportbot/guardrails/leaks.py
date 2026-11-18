"""Detect wallet secrets that a member pasted into a chat.

Two kinds of secret are recognized:

* A BIP-39 recovery phrase: a run of 12 or more consecutive words from the English
  wordlist. A valid checksum on a standard-length window raises confidence.
* A raw private key: 64 hexadecimal characters, but only when the words around it say
  so. A transaction hash has exactly the same shape, and members paste transaction
  hashes all the time when they ask for help, so hex on its own is left alone.

A `Leak` describes where the secret is and what kind it is. It never carries the
secret itself, so a finding can be logged or stored without repeating it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum

from supportbot.guardrails.bip39 import STANDARD_LENGTHS, has_valid_checksum, word_numbers

MIN_PHRASE_WORDS = min(STANDARD_LENGTHS)
# A run without a valid checksum still counts when its words are varied. This keeps a
# mistyped or partly edited phrase covered while ignoring chants of one or two list
# words ("moon moon moon ...").
MIN_DISTINCT_WORDS = 8
# How far from a hex string its describing words may be, in characters.
KEY_CONTEXT_CHARS = 80

_WORD_RE = re.compile(r"[A-Za-z]+")
_HEX_64_RE = re.compile(r"(?<![0-9A-Za-z])(?:0x)?[0-9a-fA-F]{64}(?![0-9A-Za-z])")
_KEY_CUE_RE = re.compile(r"\b(?:private|priv|secret)[\s_-]*keys?\b|\bprivkeys?\b", re.IGNORECASE)
_HASH_CUE_RE = re.compile(r"\b(?:tx|txn|txid|txhash|hash|transactions?)\b|/tx/", re.IGNORECASE)


class LeakKind(StrEnum):
    SEED_PHRASE = "seed_phrase"
    PRIVATE_KEY = "private_key"


_PLACEHOLDERS = {
    LeakKind.SEED_PHRASE: "[removed: possible recovery phrase]",
    LeakKind.PRIVATE_KEY: "[removed: possible private key]",
}


@dataclass(frozen=True, slots=True)
class Leak:
    """Location and kind of a suspected secret. Deliberately holds no secret text."""

    kind: LeakKind
    start: int
    end: int
    word_count: int = 0  # recovery phrases only
    checksum_valid: bool = False  # recovery phrases only


def find_leaks(text: str) -> list[Leak]:
    """Return every suspected secret in `text`, in order of appearance."""
    leaks = [*_find_seed_phrases(text), *_find_private_keys(text)]
    return sorted(leaks, key=lambda leak: leak.start)


def redact(text: str) -> str:
    """Replace every suspected secret in `text` with a neutral placeholder."""
    pieces: list[str] = []
    position = 0
    for leak in find_leaks(text):
        if leak.start < position:
            continue
        pieces.append(text[position : leak.start])
        pieces.append(_PLACEHOLDERS[leak.kind])
        position = leak.end
    pieces.append(text[position:])
    return "".join(pieces)


def _find_seed_phrases(text: str) -> Iterator[Leak]:
    numbers = word_numbers()
    run: list[re.Match[str]] = []
    for match in _WORD_RE.finditer(text):
        if match.group().lower() in numbers:
            run.append(match)
            continue
        yield from _leak_from_run(run)
        run = []
    yield from _leak_from_run(run)


def _leak_from_run(run: Sequence[re.Match[str]]) -> Iterator[Leak]:
    if len(run) < MIN_PHRASE_WORDS:
        return
    words = [match.group().lower() for match in run]
    checksum_valid = _contains_valid_phrase(words)
    if checksum_valid or len(set(words)) >= MIN_DISTINCT_WORDS:
        yield Leak(LeakKind.SEED_PHRASE, run[0].start(), run[-1].end(), len(run), checksum_valid)


def _contains_valid_phrase(words: Sequence[str]) -> bool:
    """Check every standard-length window, since ordinary list words may surround a phrase."""
    return any(
        has_valid_checksum(words[start : start + length])
        for length in STANDARD_LENGTHS
        for start in range(len(words) - length + 1)
    )


def _find_private_keys(text: str) -> Iterator[Leak]:
    key_cues = [match.span() for match in _KEY_CUE_RE.finditer(text)]
    if not key_cues:
        return
    hash_cues = [match.span() for match in _HASH_CUE_RE.finditer(text)]
    for match in _HEX_64_RE.finditer(text):
        key_distance = _nearest(match.span(), key_cues)
        if key_distance <= KEY_CONTEXT_CHARS and key_distance < _nearest(match.span(), hash_cues):
            yield Leak(LeakKind.PRIVATE_KEY, match.start(), match.end())


def _nearest(span: tuple[int, int], cues: Sequence[tuple[int, int]]) -> float:
    """Smallest gap in characters between `span` and any cue; infinite when there is none."""
    start, end = span
    gaps = [max(cue_start - end, start - cue_end, 0) for cue_start, cue_end in cues]
    return min(gaps, default=float("inf"))
