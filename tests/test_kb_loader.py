from pathlib import Path

import pytest

from supportbot.kb.loader import (
    KnowledgeBaseError,
    load_knowledge_base,
    split_markdown,
    to_plain_text,
)

SAMPLE_KB = Path(__file__).resolve().parent.parent / "sample_kb"


def test_document_is_split_on_headings_with_title_and_labels() -> None:
    markdown = (
        "# Swap fees\n\nIntro paragraph.\n\n"
        "## How much is the fee?\n\nIt is 0.25%.\n\n"
        "### Stablecoins\n\nIt is 0.10%.\n"
    )

    sections = split_markdown(markdown, source="fees.md")

    assert [(s.heading, s.text) for s in sections] == [
        ("", "Intro paragraph."),
        ("How much is the fee?", "It is 0.25%."),
        ("Stablecoins", "It is 0.10%."),
    ]
    assert {s.title for s in sections} == {"Swap fees"}
    assert sections[0].label == "Swap fees"
    assert sections[1].label == "Swap fees > How much is the fee?"


def test_headings_without_text_do_not_become_sections() -> None:
    sections = split_markdown("# Title\n\n## Empty\n\n## Full\n\nBody.\n", source="a.md")

    assert [s.heading for s in sections] == ["Full"]


def test_front_matter_is_metadata_and_can_supply_the_title() -> None:
    markdown = '---\ntitle: "Bridge guide"\nnote: internal\n---\n\nBridging takes minutes.\n'

    sections = split_markdown(markdown, source="bridge.md")

    assert len(sections) == 1
    assert sections[0].title == "Bridge guide"
    assert sections[0].text == "Bridging takes minutes."


def test_title_falls_back_to_a_readable_file_name() -> None:
    sections = split_markdown("Just text.\n", source="guides/lost-seed_phrase.md")

    assert sections[0].title == "Lost seed phrase"


def test_a_hash_inside_a_code_block_is_not_a_heading() -> None:
    markdown = "# Title\n\n## Setup\n\nRun this:\n\n```\n# install\npip install x\n```\n"

    sections = split_markdown(markdown, source="a.md")

    assert len(sections) == 1
    assert sections[0].text == "Run this:\n\n# install\npip install x"


def test_plain_text_reads_like_a_chat_message() -> None:
    markdown = (
        "The **swap fee** is *0.25%*,\n"
        "see [the fee page](https://example.org/fees) or `SUPPORTBOT_KB_DIR`.\n"
        "\n"
        "> Quoted warning.\n"
        "\n"
        "- first item\n"
        "- second item\n"
        "  continued\n"
        "\n"
        "---\n"
    )

    assert to_plain_text(markdown) == (
        "The swap fee is 0.25%, see the fee page (https://example.org/fees) or SUPPORTBOT_KB_DIR.\n"
        "\n"
        "Quoted warning.\n"
        "\n"
        "- first item\n"
        "- second item continued"
    )


def test_folder_is_loaded_in_sorted_order_with_forward_slash_sources(tmp_path: Path) -> None:
    (tmp_path / "b.md").write_text("# B\n\nSecond.\n", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "a.md").write_text("# A\n\nThird.\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("# A\n\nFirst.\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")

    sections = load_knowledge_base(tmp_path)

    assert [s.source for s in sections] == ["a.md", "b.md", "nested/a.md"]


def test_missing_folder_error_names_the_setting_to_fix(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeBaseError, match="SUPPORTBOT_KB_DIR"):
        load_knowledge_base(tmp_path / "does-not-exist")


def test_folder_without_markdown_content_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "empty.md").write_text("\n", encoding="utf-8")

    with pytest.raises(KnowledgeBaseError, match="No Markdown content"):
        load_knowledge_base(tmp_path)


def test_file_that_is_not_utf8_is_reported_with_its_name(tmp_path: Path) -> None:
    (tmp_path / "legacy.md").write_bytes(b"# Caf\xe9\n\nText\n")

    with pytest.raises(KnowledgeBaseError, match=r"legacy\.md.*UTF-8"):
        load_knowledge_base(tmp_path)


def test_sample_kb_has_12_to_20_entries_and_each_says_it_is_fictional() -> None:
    files = sorted(SAMPLE_KB.glob("*.md"))

    assert 12 <= len(files) <= 20
    for path in files:
        head = path.read_text(encoding="utf-8").split("\n# ", 1)[0]
        assert "AcmeSwap is a fictional product" in head, path.name
        assert "not a real service" in head, path.name


def test_sample_kb_note_is_not_served_to_members_as_an_answer() -> None:
    sections = load_knowledge_base(SAMPLE_KB)

    assert all("fictional" not in section.text for section in sections)
    assert all(section.heading for section in sections)
