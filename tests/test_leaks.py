from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import Path

import pytest

from bip39_vectors import OFFICIAL_VECTORS, phrase_of_length
from supportbot.guardrails.bip39 import wordlist
from supportbot.guardrails.leaks import LeakKind, find_leaks, redact

HEX_64 = "9f2c4a7be1d3058c6fa1b2e47d90c3a85b6e1f42d7c9083a5e4b1c6d2f7a8e90"
PHRASE = phrase_of_length(12)
ORDINARY_ENGLISH = Path(__file__).parent / "data" / "ordinary_english.txt"


def ordinary_paragraphs() -> list[str]:
    lines = [
        line
        for line in ORDINARY_ENGLISH.read_text(encoding="utf-8").splitlines()
        if not line.startswith("#")
    ]
    return [block.strip() for block in "\n".join(lines).split("\n\n") if block.strip()]


def test_bundled_wordlist_is_the_unmodified_bip39_list():
    data = resources.files("supportbot").joinpath("data/bip39_english.txt").read_bytes()
    assert hashlib.sha256(data).hexdigest() == (
        "2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda"
    )
    assert len(wordlist()) == 2048
    assert (wordlist()[0], wordlist()[-1]) == ("abandon", "zoo")


@pytest.mark.parametrize("phrase", [phrase for _entropy, phrase in OFFICIAL_VECTORS])
def test_official_test_vector_is_detected_with_a_valid_checksum(phrase):
    (leak,) = find_leaks(f"ok here it is: {phrase} - does that help?")
    assert leak.kind is LeakKind.SEED_PHRASE
    assert leak.checksum_valid


@pytest.mark.parametrize("length", [12, 15, 18, 21, 24])
def test_every_standard_phrase_length_is_detected(length):
    (leak,) = find_leaks(phrase_of_length(length))
    assert leak.word_count == length
    assert leak.checksum_valid


@pytest.mark.parametrize("separator", [", ", "\n", " - ", "  ", ". "])
def test_punctuation_and_line_breaks_do_not_hide_a_phrase(separator):
    assert len(find_leaks(separator.join(PHRASE.split()))) == 1


def test_numbered_and_uppercase_phrase_is_detected():
    numbered = " ".join(f"{n}. {word.upper()}" for n, word in enumerate(PHRASE.split(), 1))
    assert len(find_leaks(numbered)) == 1


def test_twelve_varied_list_words_are_caught_whatever_their_checksum():
    # A mistyped or partly edited phrase no longer has a valid checksum. It is still a leak.
    words = wordlist()[100:1300:100]
    assert len(words) == 12
    assert len(find_leaks(" ".join(words))) == 1


def test_bare_list_of_list_words_is_flagged_by_design():
    # Fourteen consecutive BIP-39 words. Nothing tells this from a comma-separated recovery
    # phrase, so the detector takes the cautious side. The README lists this as a limitation.
    groceries = (
        "weekend: apple juice, bread, butter, cheese, coffee, rice, salt, sugar, "
        "tomato sauce, olive oil"
    )
    assert len(find_leaks(groceries)) == 1


def test_eleven_list_words_are_not_a_phrase():
    assert find_leaks(" ".join(PHRASE.split()[:11])) == []


def test_chant_of_one_list_word_is_ignored():
    assert find_leaks("moon " * 20) == []


@pytest.mark.parametrize("paragraph", ordinary_paragraphs())
def test_ordinary_english_is_never_flagged(paragraph):
    assert find_leaks(paragraph) == []


@pytest.mark.parametrize(
    "text",
    [
        f"my bridge tx 0x{HEX_64} has been pending for 2 hours",
        f"0x{HEX_64}",
        f"is it safe to post a private key? no. anyway my transaction hash is 0x{HEX_64}",
    ],
)
def test_transaction_hash_is_left_alone(text):
    assert find_leaks(text) == []


@pytest.mark.parametrize(
    "text",
    [f"my private key is {HEX_64}", f"privkey: 0x{HEX_64}", f"0x{HEX_64} is my secret key"],
)
def test_hex_described_as_a_private_key_is_a_leak(text):
    (leak,) = find_leaks(text)
    assert leak.kind is LeakKind.PRIVATE_KEY


def test_redaction_removes_the_secret_and_keeps_the_rest():
    redacted = redact(f"ok: {PHRASE} and my private key is {HEX_64}, thanks")
    assert redacted == (
        "ok: [removed: possible recovery phrase] and my private key is "
        "[removed: possible private key], thanks"
    )


def test_finding_never_carries_the_secret_itself():
    (leak,) = find_leaks(f"words: {PHRASE}")
    assert PHRASE.split()[5] not in repr(leak)
