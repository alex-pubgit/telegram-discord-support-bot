import pytest

from supportbot.kb.text import (
    normalize_question,
    question_terms,
    stem,
    strip_salutation,
    tokenize,
)


@pytest.mark.parametrize(
    ("inflected", "base"),
    [
        ("fees", "fee"),
        ("bridging", "bridge"),
        ("bridged", "bridge"),
        ("staked", "stake"),
        ("unstaking", "unstake"),
        ("swapping", "swap"),
        ("swapped", "swap"),
        ("transferred", "transfer"),
        ("taking", "take"),
        ("addresses", "address"),
        ("currencies", "currency"),
        ("recoverable", "recover"),
        ("adjustable", "adjust"),
        ("added", "add"),
        ("listings", "listing"),
    ],
)
def test_inflected_forms_share_a_stem_with_their_base(inflected: str, base: str) -> None:
    assert stem(inflected) == stem(base)


@pytest.mark.parametrize("word", ["seed", "gas", "status", "address", "string", "speed", "bonus"])
def test_words_that_only_look_inflected_are_left_alone(word: str) -> None:
    assert stem(word) == word


def test_distinct_words_do_not_collapse_into_one_stem() -> None:
    assert stem("fee") != stem("free")
    assert stem("seed") != stem("see")


def test_tokenize_drops_stopwords_numbers_and_contraction_fragments() -> None:
    assert tokenize("What's the fee for 2 swaps? I don't know!") == ["fee", "swap"]


def test_tokenize_is_case_insensitive_and_ignores_punctuation() -> None:
    assert tokenize("BRIDGE-fee, #support") == tokenize("bridge fee support")


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Hi team, what is the bridge fee?", "what is the bridge fee?"),
        ("dear support, which network?", "which network?"),
        ("Hello! How long does unstaking take", "How long does unstaking take"),
        ("gm admins: wen airdrop", "wen airdrop"),
    ],
)
def test_opening_salutation_is_removed(message: str, expected: str) -> None:
    assert strip_salutation(message) == expected


def test_addressee_words_are_kept_when_they_are_the_topic() -> None:
    # No greeting in front, so "team" and "support" are what the member is asking about.
    assert question_terms("team?") == ["team"]
    assert question_terms("support is not answering") == ["support", "answer"]


def test_question_terms_are_distinct_and_keep_their_order() -> None:
    assert question_terms("fee fee bridge fees") == ["fee", "bridg"]


def test_greeting_only_message_has_no_terms() -> None:
    assert question_terms("Hi!") == []
    assert question_terms("thanks guys") == []


def test_normalize_question_gives_one_readable_form_for_trivial_variants() -> None:
    assert normalize_question("  When is the LISTING?! ") == "when is the listing"
    assert normalize_question("when is the listing") == "when is the listing"
