from supportbot.kb.bm25 import BM25Index

DOCUMENTS = [
    ["swap", "fee", "network", "swap"],
    ["bridge", "fee", "minutes"],
    ["staking", "rewards", "monday"],
    ["swap", "minimum", "amount"],
]


def test_rare_terms_are_worth_more_than_common_ones() -> None:
    index = BM25Index(DOCUMENTS)

    assert index.idf("bridge") > index.idf("fee") > 0
    assert index.idf("never-seen") > index.idf("bridge")


def test_document_matching_more_query_terms_ranks_first() -> None:
    index = BM25Index(DOCUMENTS)

    ranked = index.rank(["bridge", "fee"], limit=3)

    assert [document for document, _ in ranked] == [1, 0]
    assert ranked[0][1] > ranked[1][1]


def test_documents_without_any_query_term_are_not_returned() -> None:
    index = BM25Index(DOCUMENTS)

    assert index.rank(["airdrop"], limit=5) == []


def test_repeating_a_query_term_does_not_change_the_score() -> None:
    index = BM25Index(DOCUMENTS)

    assert index.score(["swap", "swap", "swap"], 0) == index.score(["swap"], 0)


def test_shorter_document_wins_when_term_counts_are_equal() -> None:
    index = BM25Index([["fee", "a", "b", "c", "d", "e"], ["fee", "a"]])

    assert [document for document, _ in index.rank(["fee"], limit=2)] == [1, 0]


def test_ties_keep_document_order_so_results_are_reproducible() -> None:
    index = BM25Index([["fee", "x"], ["fee", "y"], ["fee", "z"]])

    assert [document for document, _ in index.rank(["fee"], limit=3)] == [0, 1, 2]


def test_limit_caps_the_number_of_results() -> None:
    index = BM25Index([["fee"], ["fee"], ["fee"]])

    assert len(index.rank(["fee"], limit=2)) == 2


def test_empty_index_and_empty_documents_are_handled() -> None:
    assert BM25Index([]).rank(["fee"], limit=3) == []
    assert BM25Index([[], ["fee"]]).rank(["fee"], limit=3)[0][0] == 1
