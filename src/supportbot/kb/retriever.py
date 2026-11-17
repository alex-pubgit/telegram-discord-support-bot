"""Find the knowledge base sections that best match a question, with a confidence score."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from supportbot.kb.bm25 import BM25Index
from supportbot.kb.loader import Section
from supportbot.kb.text import question_terms, tokenize

# A heading is the question a section answers, so its words count more than body words.
HEADING_WEIGHT = 2
# BM25 proposes this many candidates; confidence then decides their final order.
CANDIDATE_POOL = 5
# One matching word in body text is weak evidence that a section answers the question.
SINGLE_BODY_MATCH_FACTOR = 0.5
# Below this confidence the bot hands off instead of answering. Calibrated on the sample
# questions in tests/data/sample_kb_questions.json: it sits in the gap between the weakest
# correct answer and the strongest match for an undocumented question.
DEFAULT_MIN_CONFIDENCE = 0.6


@dataclass(frozen=True, slots=True)
class Match:
    section: Section
    score: float  # raw BM25 score, only meaningful for ranking within one question
    confidence: float  # 0.0 to 1.0, comparable across questions


class Retriever:
    """BM25 ranking plus a confidence score that says whether the best hit can be trusted.

    BM25 scores are unbounded and depend on the question, so they cannot be compared
    with a fixed threshold. Confidence is the share of the question's informative
    vocabulary that a section contains, where rare words weigh more than common ones
    and a word the knowledge base has never seen weighs the most. A question about an
    undocumented topic therefore scores low even when it shares a few common words
    with some section.
    """

    def __init__(self, sections: Sequence[Section]):
        self._sections = list(sections)
        # The text before the first sub-heading belongs to the document title.
        headings = [tokenize(section.heading or section.title) for section in sections]
        bodies = [tokenize(section.text) for section in sections]
        self._heading_terms = [frozenset(terms) for terms in headings]
        self._own_terms = [
            frozenset(heading) | frozenset(body)
            for heading, body in zip(headings, bodies, strict=True)
        ]
        # The document title gives ranking context ("ACME staking") but is shared by every
        # section of a file, so it does not count as evidence when confidence is computed.
        self._index = BM25Index(
            [
                tokenize(section.title) + heading * HEADING_WEIGHT + body
                for section, heading, body in zip(sections, headings, bodies, strict=True)
            ]
        )

    def __len__(self) -> int:
        return len(self._sections)

    def search(self, question: str, limit: int = 3) -> list[Match]:
        """Return up to `limit` sections, most trustworthy first. Empty when nothing matches."""
        terms = question_terms(question)
        if not terms:
            return []
        weights = {term: self._index.idf(term) for term in terms}
        matches = [
            Match(self._sections[index], score, self._confidence(weights, index))
            for index, score in self._index.rank(terms, max(CANDIDATE_POOL, limit))
        ]
        matches = [match for match in matches if match.confidence > 0.0]
        matches.sort(key=lambda match: (-match.confidence, -match.score))
        return matches[:limit]

    def _confidence(self, weights: dict[str, float], document: int) -> float:
        matched = [term for term in weights if term in self._own_terms[document]]
        coverage = sum(weights[term] for term in matched) / sum(weights.values())
        if len(matched) == 1 and matched[0] not in self._heading_terms[document]:
            coverage *= SINGLE_BODY_MATCH_FACTOR
        return coverage
