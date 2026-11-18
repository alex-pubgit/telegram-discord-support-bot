"""Public BIP-39 test vectors and a test-side encoder.

Every phrase in this file is a published test vector or is derived from fixed,
non-secret entropy. None of them protects a wallet. Never use them for one.

The official vectors come from the list that BIP-39 itself references:
https://github.com/trezor/python-mnemonic/blob/master/vectors.json (MIT License).
That list has no 15-word or 21-word phrases, so `mnemonic_from_entropy` builds those.
It is written independently of the production checksum code and is itself checked
against the official vectors, so the two implementations verify each other.
"""

from __future__ import annotations

import hashlib

from supportbot.guardrails.bip39 import wordlist

# (entropy as hex, phrase)
OFFICIAL_VECTORS = [
    (
        "00000000000000000000000000000000",
        "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon"
        " about",
    ),
    (
        "7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f",
        "legal winner thank year wave sausage worth useful legal winner thank yellow",
    ),
    (
        "9e885d952ad362caeb4efe34a8e91bd2",
        "ozone drill grab fiber curtain grace pudding thank cruise elder eight picnic",
    ),
    (
        "c0ba5a8e914111210f2bd131f3d5e08d",
        "scheme spot photo card baby mountain device kick cradle pact join borrow",
    ),
    (
        "6610b25967cdcca9d59875f5cb50b0ea75433311869e930b",
        "gravity machine north sort system female filter attitude volume fold club stay feature"
        " office ecology stable narrow fog",
    ),
    (
        "ffffffffffffffffffffffffffffffffffffffffffffffff",
        "zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo when",
    ),
    (
        "68a79eaca2324873eacc50cb9c6eca8cc68ea5d936f98787c60c7ebc74e6ce7c",
        "hamster diagram private dutch cause delay private meat slide toddler razor book happy"
        " fancy gospel tennis maple dilemma loan word shrug inflict delay length",
    ),
    (
        "0000000000000000000000000000000000000000000000000000000000000000",
        "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon"
        " abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon"
        " abandon art",
    ),
]

# The best-known test vector, used wherever a single throwaway phrase is needed.
TEST_PHRASE_12 = OFFICIAL_VECTORS[0][1]


def mnemonic_from_entropy(entropy: bytes) -> str:
    """Encode entropy as a BIP-39 phrase (entropy bits, then checksum bits, 11 bits per word)."""
    checksum_length = len(entropy) * 8 // 32
    bits = "".join(f"{byte:08b}" for byte in entropy)
    bits += f"{hashlib.sha256(entropy).digest()[0]:08b}"[:checksum_length]
    words = wordlist()
    return " ".join(words[int(bits[i : i + 11], 2)] for i in range(0, len(bits), 11))


def phrase_of_length(word_count: int) -> str:
    """A valid phrase of a standard length, from fixed entropy that is obviously not random."""
    entropy_bytes = word_count * 11 * 32 // 33 // 8
    return mnemonic_from_entropy(bytes(range(1, entropy_bytes + 1)))
