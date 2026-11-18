"""BIP-39 English wordlist and checksum check.

This module exists for detection only. It can tell that a sequence of words is a
well-formed recovery phrase; it has no code to turn one into a seed or a key.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from functools import cache
from importlib import resources

WORDLIST_SIZE = 2048
BITS_PER_WORD = 11
# Word counts that BIP-39 defines, for 128, 160, 192, 224 and 256 bits of entropy.
STANDARD_LENGTHS = (12, 15, 18, 21, 24)


@cache
def wordlist() -> tuple[str, ...]:
    """The 2048 BIP-39 English words in their official order."""
    data = resources.files("supportbot").joinpath("data", "bip39_english.txt")
    words = tuple(data.read_text(encoding="ascii").split())
    if len(words) != WORDLIST_SIZE:
        raise RuntimeError(
            f"The bundled BIP-39 wordlist has {len(words)} words instead of {WORDLIST_SIZE}. "
            "Reinstall the package."
        )
    return words


@cache
def word_numbers() -> dict[str, int]:
    """Map each word to its 11-bit number (its position in the list)."""
    return {word: number for number, word in enumerate(wordlist())}


def has_valid_checksum(words: Sequence[str]) -> bool:
    """True when `words` is a standard-length BIP-39 phrase whose checksum matches.

    A phrase encodes its entropy followed by the first `entropy_bits / 32` bits of the
    entropy's SHA-256 hash. Random wordlist words pass this check only 1 time in 16
    (12 words) to 1 time in 256 (24 words), so a match is strong evidence of a real phrase.
    """
    if len(words) not in STANDARD_LENGTHS:
        return False
    numbers = word_numbers()
    value = 0
    for word in words:
        number = numbers.get(word)
        if number is None:
            return False
        value = (value << BITS_PER_WORD) | number
    total_bits = len(words) * BITS_PER_WORD
    checksum_bits = total_bits // 33
    entropy = (value >> checksum_bits).to_bytes((total_bits - checksum_bits) // 8, "big")
    expected = hashlib.sha256(entropy).digest()[0] >> (8 - checksum_bits)
    return value & ((1 << checksum_bits) - 1) == expected
