import json
from pathlib import Path

import pytest

from supportbot.kb.loader import Section, load_knowledge_base
from supportbot.kb.retriever import DEFAULT_MIN_CONFIDENCE, Retriever

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / "tests" / "data" / "sample_kb_questions.json").read_text("utf-8"))


def section(heading: str, text: str, *, title: str = "Guide", source: str = "guide.md") -> Section:
    return Section(source=source, title=title, heading=heading, text=text)


@pytest.fixture(scope="module")
def sample_retriever() -> Retriever:
    return Retriever(load_knowledge_base(ROOT / "sample_kb"))


def test_fully_covered_question_has_full_confidence() -> None:
    retriever = Retriever(
        [
            section("How much is the bridge fee?", "The bridge fee is 0.05%."),
            section("How long does unstaking take?", "Unstaking takes 7 days."),
        ]
    )

    best = retriever.search("what is the bridge fee")[0]

    assert best.section.heading == "How much is the bridge fee?"
    assert best.confidence == pytest.approx(1.0)


def test_word_the_knowledge_base_never_uses_pulls_confidence_down() -> None:
    retriever = Retriever(
        [
            section("How much is the bridge fee?", "The bridge fee is 0.05%."),
            section("How long does unstaking take?", "Unstaking takes 7 days."),
        ]
    )

    documented = retriever.search("bridge fee")[0]
    undocumented = retriever.search("bridge fee on arbitrum")[0]

    assert undocumented.section == documented.section
    assert undocumented.confidence < DEFAULT_MIN_CONFIDENCE < documented.confidence


def test_single_word_found_only_in_body_text_is_weak_evidence() -> None:
    retriever = Retriever(
        [
            section("Will an admin message me first?", "Admins and team members never do."),
            section("Is there an airdrop?", "No airdrop is announced."),
        ]
    )

    body_only = retriever.search("who is on the team?")[0]
    in_heading = retriever.search("airdrop?")[0]

    assert body_only.confidence == pytest.approx(0.5)
    assert in_heading.confidence == pytest.approx(1.0)


def test_document_title_alone_is_not_evidence() -> None:
    retriever = Retriever(
        [
            section("Is there a validation tool?", "No such tool exists.", title="Support"),
            section("Which networks work?", "Three networks.", title="Networks"),
        ]
    )

    assert retriever.search("support") == []


def test_introduction_is_matched_through_the_document_title() -> None:
    retriever = Retriever(
        [
            section("", "The fee is 0.25% per swap.", title="What is the swap fee?"),
            section("", "Bridging takes minutes.", title="How long does bridging take?"),
        ]
    )

    best = retriever.search("swap fee?")[0]

    assert best.section.title == "What is the swap fee?"
    assert best.confidence == pytest.approx(1.0)


def test_candidate_that_covers_the_rarer_words_is_preferred() -> None:
    retriever = Retriever(
        [
            section("Which network is the token on?", "The token is on one network. Token token."),
            section("Why do I need gas?", "You pay gas in ETH on Ethereum."),
            section("What is a token?", "A token is an asset."),
            section("Token list", "Every token we know."),
        ]
    )

    best = retriever.search("gas token on ethereum")[0]

    assert best.section.heading == "Why do I need gas?"


def test_question_without_informative_words_matches_nothing() -> None:
    retriever = Retriever([section("Fees", "The fee is 0.25%.")])

    assert retriever.search("hi, can you help me please?") == []
    assert retriever.search("") == []


def test_limit_caps_results_and_orders_them_by_confidence() -> None:
    retriever = Retriever(
        [section(f"Fee question {n}", f"The fee number {n} is here.") for n in range(8)]
        + [section("Bridge fee", "The bridge fee is small.")]
    )

    matches = retriever.search("bridge fee", limit=2)

    assert len(matches) == 2
    assert matches[0].section.heading == "Bridge fee"
    assert matches[0].confidence >= matches[1].confidence


@pytest.mark.parametrize("case", CASES["answerable"], ids=lambda case: case["question"])
def test_sample_question_is_answered_from_the_right_entry(
    sample_retriever: Retriever, case: dict[str, str]
) -> None:
    best = sample_retriever.search(case["question"])[0]

    assert best.section.source == case["source"]
    assert best.confidence >= DEFAULT_MIN_CONFIDENCE


@pytest.mark.parametrize("question", CASES["handoff"] + CASES["known_misses"])
def test_undocumented_or_unclear_sample_question_stays_below_the_threshold(
    sample_retriever: Retriever, question: str
) -> None:
    matches = sample_retriever.search(question)

    assert not matches or matches[0].confidence < DEFAULT_MIN_CONFIDENCE


def test_threshold_has_a_margin_on_both_sides(sample_retriever: Retriever) -> None:
    """A threshold that only just separates the two groups would be luck, not calibration."""
    weakest_answer = min(
        sample_retriever.search(case["question"])[0].confidence for case in CASES["answerable"]
    )
    strongest_undocumented = max(
        (sample_retriever.search(question) or [None])[0].confidence
        for question in CASES["handoff"]
        if sample_retriever.search(question)
    )

    assert weakest_answer - DEFAULT_MIN_CONFIDENCE >= 0.05
    assert DEFAULT_MIN_CONFIDENCE - strongest_undocumented >= 0.05
