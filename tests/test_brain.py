from __future__ import annotations

import pytest

from bip39_vectors import phrase_of_length
from supportbot.answer import BackendError
from supportbot.brain import (
    ADVICE_REFUSAL,
    DEFAULT_SAFETY_NOTICE,
    HELP,
    ChatKind,
    DeleteMessage,
    Message,
    NotifyModerators,
    Reply,
    SupportBrain,
)
from supportbot.guardrails.ratelimit import RateLimiter

PHRASE = phrase_of_length(12)
HEX_64 = "9f2c4a7be1d3058c6fa1b2e47d90c3a85b6e1f42d7c9083a5e4b1c6d2f7a8e90"


def msg(text: str, **fields) -> Message:
    defaults = {"platform": "test", "chat_id": "c1", "user_id": "u1", "user_name": "Alice"}
    return Message(text=text, **{**defaults, **fields})


def group(text: str, **fields) -> Message:
    return msg(text, chat_kind=ChatKind.GROUP, **fields)


def test_answer_comes_with_its_source(brain):
    (reply,) = brain.handle(msg("How much is the bridge fee?"))
    assert "0.05%" in reply.text
    assert reply.text.endswith("Source: Bridging between networks > How much is the bridge fee?")


def test_group_message_not_meant_for_the_bot_is_ignored(brain):
    assert brain.handle(group("How much is the bridge fee?", addressed=False)) == []


def test_group_message_meant_for_the_bot_is_answered(brain):
    (reply,) = brain.handle(group("How much is the bridge fee?", addressed=True))
    assert "0.05%" in reply.text


def test_undocumented_question_opens_a_ticket_and_notifies_moderators(brain, store):
    reply, notice = brain.handle(msg("When will ACME be listed on an exchange?"))
    assert isinstance(reply, Reply)
    assert "ticket #1" in reply.text
    assert notice == NotifyModerators(
        "Ticket #1 from Alice on test: When will ACME be listed on an exchange?"
    )
    assert [ticket.question for ticket in store.open_tickets()] == [
        "When will ACME be listed on an exchange?"
    ]


def test_human_command_hands_off_even_a_documented_question(brain, store):
    _reply, notice = brain.handle(msg("/human How much is the bridge fee?"))
    assert isinstance(notice, NotifyModerators)
    assert len(store.open_tickets()) == 1


def test_outage_of_the_answer_service_becomes_a_handoff(store):
    class Down:
        def answer(self, question: str):
            raise BackendError("unreachable")

    brain = SupportBrain(Down(), store, RateLimiter(3, 20.0))
    reply, notice = brain.handle(msg("How much is the bridge fee?"))
    assert "passed it to the team" in reply.text
    assert isinstance(notice, NotifyModerators)


@pytest.mark.parametrize("question", ["should I buy ACME now?", "price prediction for ACME?"])
def test_investment_question_gets_the_fixed_refusal(brain, question):
    assert brain.handle(msg(question)) == [Reply(ADVICE_REFUSAL)]


def test_question_about_wallet_recovery_carries_the_safety_notice(brain):
    (reply,) = brain.handle(msg("I lost my seed phrase, can you recover it?"))
    assert reply.text.endswith(DEFAULT_SAFETY_NOTICE)


def test_ordinary_question_carries_no_safety_notice(brain):
    (reply,) = brain.handle(msg("How much is the bridge fee?"))
    assert DEFAULT_SAFETY_NOTICE not in reply.text


@pytest.mark.parametrize("addressed", [True, False])
def test_leaked_phrase_is_deleted_whether_or_not_the_bot_was_addressed(brain, addressed):
    delete, warning = brain.handle(group(f"my words are {PHRASE}", addressed=addressed))
    assert delete == DeleteMessage()
    assert "wallet recovery phrase" in warning.text
    assert "compromised" in warning.text
    assert PHRASE not in warning.text


def test_leaked_phrase_never_reaches_the_database(brain, store):
    brain.handle(msg(f"/human please help {PHRASE}"))
    dump = "\n".join(store._db.iterdump())
    assert PHRASE.split()[4] not in dump
    assert store.open_tickets() == []
    assert store.summary().outcomes == {"blocked": 1}


def test_transaction_hash_in_a_question_is_not_treated_as_a_secret(brain):
    actions = brain.handle(msg(f"my bridge tx 0x{HEX_64} is still pending, what should I do?"))
    assert not any(isinstance(action, DeleteMessage) for action in actions)


@pytest.mark.parametrize("command", ["/tickets", "/resolve 1", "/stats"])
def test_moderator_command_is_refused_to_members(brain, command):
    assert brain.handle(msg(command)) == [Reply("Only moderators can use that command.")]


def test_moderator_lists_then_resolves_a_ticket(brain):
    brain.handle(msg("When will ACME be listed on an exchange?"))
    (listing,) = brain.handle(msg("/tickets", user_id="mod", is_admin=True))
    assert listing.text == "#1 Alice (test): When will ACME be listed on an exchange?"
    resolve = brain.handle(msg("/resolve 1", user_id="mod", is_admin=True))
    assert resolve == [Reply("Ticket #1 resolved.")]
    assert brain.handle(msg("/resolve 1", user_id="mod", is_admin=True)) == [
        Reply("No open ticket #1.")
    ]
    assert brain.handle(msg("/tickets", user_id="mod", is_admin=True)) == [
        Reply("No open tickets.")
    ]


def test_burst_is_answered_then_one_warning_then_silence(brain, clock):
    for _ in range(3):
        assert len(brain.handle(msg("How much is the bridge fee?"))) == 1
    (warning,) = brain.handle(msg("How much is the bridge fee?"))
    assert "Please wait" in warning.text
    assert brain.handle(msg("How much is the bridge fee?")) == []
    clock.advance(60)
    assert len(brain.handle(msg("How much is the bridge fee?"))) == 1


def test_moderators_are_not_rate_limited(brain):
    for _ in range(10):
        assert len(brain.handle(msg("/tickets", is_admin=True))) == 1


def test_command_addressed_to_the_bot_by_name_is_understood(brain):
    (reply,) = brain.handle(group("/ask@AcmeHelpBot How much is the bridge fee?"))
    assert "0.05%" in reply.text


@pytest.mark.parametrize("text", ["/start", "/help", "/ask", "/unknown thing"])
def test_empty_or_unknown_command_gets_the_help_text(brain, text):
    assert brain.handle(msg(text)) == [Reply(HELP)]
