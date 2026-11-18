from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import httpx2 as httpx
import pytest

from supportbot.answer import BackendError, RagApiBackend, _trim
from supportbot.storage import Store, format_summary


def test_member_id_is_stored_only_as_a_salted_hash(tmp_path: Path):
    path = tmp_path / "bot.sqlite3"
    store = Store(path, salt="pepper")
    store.record("telegram", "123456789", "answered", source="Fees")
    store.close()
    assert b"123456789" not in path.read_bytes()


def test_same_member_hashes_differently_under_another_salt():
    first, second = Store(":memory:", salt="a"), Store(":memory:", salt="b")
    for store in (first, second):
        store.record("telegram", "42", "answered")
    hashes = [s._db.execute("SELECT member_hash FROM events").fetchone() for s in (first, second)]
    assert hashes[0] != hashes[1]


def test_question_text_is_kept_only_for_unanswered_questions(store):
    store.record("test", "u1", "answered", source="Fees", question="What is the fee?")
    store.record("test", "u1", "handoff", question="When is the listing?")
    stored = [row[0] for row in store._db.execute("SELECT question FROM events ORDER BY id")]
    assert stored == [None, "When is the listing?"]


def test_question_text_can_be_switched_off_entirely():
    store = Store(":memory:", salt="s", store_unanswered=False)
    store.record("test", "u1", "handoff", question="When is the listing?")
    assert store._db.execute("SELECT question FROM events").fetchone() == (None,)


def test_summary_groups_rewordings_and_ignores_old_events(store, clock):
    store.record("test", "u1", "handoff", question="An old question")
    clock.advance(timedelta(days=8).total_seconds())
    store.record("test", "u1", "handoff", question="When is the listing?")
    store.record("test", "u2", "handoff", question="when is the LISTING")
    store.record("test", "u3", "answered", source="Fees > Swap fee", confidence=0.9)

    summary = store.summary(days=7)
    assert summary.unanswered == [("when is the listing", 2)]
    assert summary.sources == [("Fees > Swap fee", 1)]
    assert summary.answer_rate == pytest.approx(1 / 3)
    assert format_summary(summary).splitlines() == [
        "Last 7 days: 1 answered (33%), 2 handed off, 0 refused, 0 leaks removed, 0 rate-limited",
        "Unanswered most often (documentation to write next):",
        "  2x when is the listing",
        "Most used sections:",
        "  1x Fees > Swap fee",
    ]


def test_ticket_can_be_resolved_once(store):
    ticket = store.open_ticket("test", "c1", "Alice", "Where is my transfer?")
    assert store.resolve(ticket)
    assert not store.resolve(ticket)
    assert not store.resolve(999)


def rag(handler) -> RagApiBackend:
    return RagApiBackend("http://rag.test", transport=httpx.MockTransport(handler))


def test_rag_api_answer_keeps_text_sources_and_best_score():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        citation = {"n": 1, "source": "bridge.md", "title": "Bridge", "snippet": "..."}
        citations = [
            {**citation, "heading": "Bridge fee", "score": 0.71},
            {**citation, "heading": "", "score": 0.4},
        ]
        body = {"answer": "It is 0.05%. [1]", "refused": False, "citations": citations}
        return httpx.Response(200, json=body)

    answer = rag(handler).answer("What is the bridge fee?")
    assert seen["url"] == "http://rag.test/ask"
    assert answer.text == "It is 0.05%. [1]"
    assert answer.source == "Bridge > Bridge fee; Bridge"
    assert answer.confidence == 0.71


def test_rag_api_refusal_means_no_answer():
    body = {"answer": "I don't know.", "refused": True, "citations": []}
    assert rag(lambda _request: httpx.Response(200, json=body)).answer("?") is None


@pytest.mark.parametrize(
    "reply",
    [httpx.Response(500, text="boom"), httpx.Response(200, json={"answer": "no flag"})],
)
def test_rag_api_failure_is_reported_as_a_backend_error(reply):
    with pytest.raises(BackendError):
        rag(lambda _request: reply).answer("?")


def test_rag_api_network_failure_is_reported_as_a_backend_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(BackendError, match="unreachable"):
        rag(handler).answer("?")


def test_long_section_is_cut_at_a_sentence_end():
    text = "First sentence here. Second sentence follows. " + "word " * 100
    assert _trim(text, 60) == "First sentence here. Second sentence follows."
    assert _trim("short", 60) == "short"
