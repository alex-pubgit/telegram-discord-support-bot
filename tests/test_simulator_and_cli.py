from __future__ import annotations

import pytest

from conftest import SAMPLE_KB
from supportbot.brain import ChatKind, SupportBrain
from supportbot.cli import main
from supportbot.guardrails.ratelimit import RateLimiter
from supportbot.simulator import ScriptError, parse_line, run_script
from supportbot.storage import Store

EXAMPLES = SAMPLE_KB.parent / "examples"
SCRIPT = EXAMPLES / "demo.script"
TRANSCRIPT = EXAMPLES / "demo.transcript.txt"


def test_demo_script_reproduces_the_published_transcript(sample_backend):
    brain = SupportBrain(
        sample_backend, Store(":memory:", salt="simulator"), RateLimiter(1000, 1.0)
    )
    script = SCRIPT.read_text(encoding="utf-8").splitlines()
    expected = TRANSCRIPT.read_text(encoding="utf-8").splitlines()
    assert list(run_script(script, brain)) == expected


def test_published_transcript_does_not_contain_the_leaked_phrase():
    transcript = TRANSCRIPT.read_text(encoding="utf-8")
    assert "abandon abandon" not in transcript
    assert "[removed: possible recovery phrase]" in transcript
    assert "(bot deleted this message)" in transcript


@pytest.mark.parametrize(
    ("line", "kind", "addressed", "admin", "text"),
    [
        ("alice: @bot what are the fees?", ChatKind.GROUP, True, False, "what are the fees?"),
        ("alice: what are the fees?", ChatKind.GROUP, False, False, "what are the fees?"),
        ("mia (mod): /tickets", ChatKind.GROUP, True, True, "/tickets"),
        ("dan (dm): hello", ChatKind.DIRECT, True, False, "hello"),
    ],
)
def test_script_line_is_read_as_a_chat_message(line, kind, addressed, admin, text):
    message = parse_line(line)
    assert (message.chat_kind, message.addressed, message.is_admin, message.text) == (
        kind,
        addressed,
        admin,
        text,
    )


def test_unreadable_script_line_is_reported():
    with pytest.raises(ScriptError, match="name: message"):
        parse_line("no speaker here")


@pytest.fixture
def clean_environment(tmp_path, monkeypatch):
    """Run from an empty folder with no bot settings, so a developer's .env cannot leak in."""
    monkeypatch.chdir(tmp_path)
    for name in ("TELEGRAM_BOT_TOKEN", "DISCORD_BOT_TOKEN", "SUPPORTBOT_HASH_SALT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SUPPORTBOT_KB_DIR", str(SAMPLE_KB))


def test_simulate_command_prints_the_transcript(clean_environment, capsys):
    assert main(["simulate", "--script", str(SCRIPT)]) == 0
    assert capsys.readouterr().out == TRANSCRIPT.read_text(encoding="utf-8")


def test_script_saved_with_a_byte_order_mark_is_read(clean_environment, tmp_path, capsys):
    script = tmp_path / "bom.script"
    script.write_text("alice: @bot How much is the bridge fee?\n", encoding="utf-8-sig")
    assert main(["simulate", "--script", str(script)]) == 0
    assert "0.05%" in capsys.readouterr().out


def test_report_without_a_database_says_what_to_do(clean_environment, capsys):
    assert main(["report"]) == 1
    assert "No database" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("platform", "variable"),
    [("telegram", "TELEGRAM_BOT_TOKEN"), ("discord", "DISCORD_BOT_TOKEN")],
)
def test_run_without_a_token_names_the_missing_variable(
    clean_environment, capsys, platform, variable
):
    assert main(["run", platform]) == 1
    assert variable in capsys.readouterr().err


def test_run_without_a_hash_salt_is_refused(clean_environment, monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "4242:TEST")
    assert main(["run", "telegram"]) == 1
    assert "SUPPORTBOT_HASH_SALT" in capsys.readouterr().err


def test_missing_knowledge_base_folder_is_reported(clean_environment, monkeypatch, capsys):
    monkeypatch.setenv("SUPPORTBOT_KB_DIR", "does-not-exist")
    assert main(["simulate", "--script", str(SCRIPT)]) == 1
    assert "does-not-exist" in capsys.readouterr().err


def test_invalid_admin_entry_is_reported(clean_environment, monkeypatch, capsys):
    monkeypatch.setenv("SUPPORTBOT_ADMINS", "alice")
    assert main(["simulate", "--script", str(SCRIPT)]) == 1
    assert "platform:user_id" in capsys.readouterr().err
