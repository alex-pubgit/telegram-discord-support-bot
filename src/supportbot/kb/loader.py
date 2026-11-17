"""Load a folder of Markdown files into answerable sections."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(\n|\Z)", re.DOTALL)
_FRONT_MATTER_TITLE_RE = re.compile(r"^title:\s*[\"']?(.+?)[\"']?\s*$", re.MULTILINE)
_RULE_RE = re.compile(r"^([-*_])(\s*\1){2,}$")
_QUOTE_PREFIX_RE = re.compile(r"^\s*(>\s?)+")
_BLOCK_START_RE = re.compile(r"^([-*+]\s|\d+[.)]\s|\|)")
_BLANK_RUN_RE = re.compile(r"\n{3,}")

_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)[^)]*\)")
_CODE_RE = re.compile(r"`([^`]+)`")
_STAR_EMPHASIS_RE = re.compile(r"(\*\*|\*)(?=\S)(.+?)(?<=\S)\1")
# Underscores only mark emphasis at word boundaries, so SETTING_NAMES stay intact.
_UNDERSCORE_EMPHASIS_RE = re.compile(r"(?<!\w)(__|_)(?=\S)(.+?)(?<=\S)\1(?!\w)")


class KnowledgeBaseError(Exception):
    """The knowledge base folder is missing, unreadable or empty."""


@dataclass(frozen=True, slots=True)
class Section:
    """One answerable unit: a heading and the text below it."""

    source: str  # file path relative to the knowledge base folder, with forward slashes
    title: str  # document title (first level-one heading, front matter title, or file name)
    heading: str  # section heading; empty for the introduction before the first sub-heading
    text: str  # plain text shown to members

    @property
    def label(self) -> str:
        """Human-readable source reference, for example "Swap fees > Stablecoin swaps"."""
        return f"{self.title} > {self.heading}" if self.heading else self.title


def load_knowledge_base(folder: Path) -> list[Section]:
    """Read every Markdown file under `folder` and split it into sections.

    Files are read in sorted order so the result, and therefore retrieval
    tie-breaking, is the same on every machine.
    """
    if not folder.is_dir():
        raise KnowledgeBaseError(
            f"Knowledge base folder not found: {folder}. "
            "Set SUPPORTBOT_KB_DIR to a folder of Markdown (.md) files."
        )
    sections: list[Section] = []
    for path in sorted(folder.rglob("*.md")):
        try:
            markdown = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise KnowledgeBaseError(
                f"Could not read {path}: {exc}. Knowledge base files must be UTF-8 text."
            ) from exc
        sections.extend(split_markdown(markdown, source=path.relative_to(folder).as_posix()))
    if not sections:
        raise KnowledgeBaseError(
            f"No Markdown content found in {folder}. "
            "Add .md files with a '# Title' and '## Question' headings."
        )
    return sections


def split_markdown(markdown: str, *, source: str) -> list[Section]:
    """Split one document on its `#` headings. Sections without body text are dropped."""
    title = ""
    front_matter = _FRONT_MATTER_RE.match(markdown)
    if front_matter:
        declared = _FRONT_MATTER_TITLE_RE.search(front_matter.group(1))
        title = declared.group(1) if declared else ""
        markdown = markdown[front_matter.end() :]

    heading = ""
    saw_level_one = False
    body: list[str] = []
    sections: list[Section] = []
    in_fence = False

    def flush() -> None:
        text = to_plain_text("\n".join(body))
        if text:
            sections.append(Section(source, title or _title_from_path(source), heading, text))
        body.clear()

    for line in markdown.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        match = None if in_fence else _HEADING_RE.match(line)
        if match is None:
            body.append(line)
            continue
        flush()
        heading_text = _strip_inline_markup(match.group(2))
        if len(match.group(1)) == 1 and not saw_level_one:
            title, heading, saw_level_one = heading_text, "", True
        else:
            heading = heading_text
    flush()
    return sections


def to_plain_text(markdown: str) -> str:
    """Turn a Markdown block into text that reads well in a chat message.

    Wrapped lines of a paragraph are joined, list items and table rows keep their own
    line, code blocks are kept verbatim, and inline markup is removed.
    """
    lines: list[str] = []
    in_fence = False
    paragraph_open = False
    for raw in markdown.splitlines():
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            paragraph_open = False
            continue
        if in_fence:
            lines.append(raw.rstrip())
            continue
        line = _QUOTE_PREFIX_RE.sub("", raw).strip()
        if not line or _RULE_RE.match(line):
            lines.append("")
            paragraph_open = False
            continue
        line = _strip_inline_markup(line)
        if paragraph_open and not _BLOCK_START_RE.match(line):
            lines[-1] = f"{lines[-1]} {line}"
        else:
            lines.append(line)
        paragraph_open = True
    return _BLANK_RUN_RE.sub("\n\n", "\n".join(lines)).strip()


def _strip_inline_markup(text: str) -> str:
    text = _IMAGE_RE.sub(r"\1", text)
    text = _LINK_RE.sub(r"\1 (\2)", text)
    text = _CODE_RE.sub(r"\1", text)
    text = _STAR_EMPHASIS_RE.sub(r"\2", text)
    return _UNDERSCORE_EMPHASIS_RE.sub(r"\2", text)


def _title_from_path(source: str) -> str:
    stem = Path(source).stem.replace("-", " ").replace("_", " ").strip()
    return stem[:1].upper() + stem[1:]
