"""A compact Okapi BM25 index over pre-tokenized documents."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence


class BM25Index:
    """Rank short documents against a query.

    `k1` controls how quickly repeated terms stop adding score and `b` how strongly
    long documents are penalized. The defaults are the usual textbook values.
    """

    def __init__(self, documents: Sequence[Sequence[str]], *, k1: float = 1.5, b: float = 0.75):
        self._k1 = k1
        self._b = b
        self._term_counts = [Counter(document) for document in documents]
        self._lengths = [len(document) for document in documents]
        self._average_length = sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        self._document_frequency: Counter[str] = Counter()
        for counts in self._term_counts:
            self._document_frequency.update(counts.keys())

    def __len__(self) -> int:
        return len(self._term_counts)

    def idf(self, term: str) -> float:
        """Inverse document frequency. Always positive; highest for terms no document has."""
        frequency = self._document_frequency.get(term, 0)
        return math.log(1.0 + (len(self) - frequency + 0.5) / (frequency + 0.5))

    def contains(self, document: int, term: str) -> bool:
        return term in self._term_counts[document]

    def score(self, query_terms: Sequence[str], document: int) -> float:
        counts = self._term_counts[document]
        if not counts:
            return 0.0
        length_ratio = self._lengths[document] / self._average_length
        norm = self._k1 * (1.0 - self._b + self._b * length_ratio)
        total = 0.0
        for term in set(query_terms):
            frequency = counts.get(term, 0)
            if frequency:
                total += self.idf(term) * frequency * (self._k1 + 1.0) / (frequency + norm)
        return total

    def rank(self, query_terms: Sequence[str], limit: int) -> list[tuple[int, float]]:
        """Best-scoring documents first. Documents with no matching term are left out.

        Ties keep the original document order, which makes results reproducible.
        """
        scored = [(index, self.score(query_terms, index)) for index in range(len(self))]
        matches = [(index, score) for index, score in scored if score > 0.0]
        matches.sort(key=lambda pair: -pair[1])
        return matches[:limit]
