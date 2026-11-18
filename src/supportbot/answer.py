"""Where answers come from: the local knowledge base, or an external RAG service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx2 as httpx

from supportbot.kb.retriever import DEFAULT_MIN_CONFIDENCE, Retriever


@dataclass(frozen=True, slots=True)
class BackendAnswer:
    text: str
    source: str
    confidence: float | None = None


class BackendError(Exception):
    """The answer service could not be used. The brain turns this into a handoff."""


class AnswerBackend(Protocol):
    def answer(self, question: str) -> BackendAnswer | None:
        """An answer grounded in the documentation, or None when there is no reliable one."""
        ...


def _trim(text: str, limit: int) -> str:
    """Cut at the last sentence that fits, so a chat message never ends mid-sentence."""
    if len(text) <= limit:
        return text
    cut = max(text.rfind(mark, 0, limit) for mark in (". ", "? ", "! ", ".\n"))
    if cut > limit // 2:
        return text[: cut + 1]
    return text[:limit].rsplit(" ", 1)[0] + " ..."


class KnowledgeBaseBackend:
    """Reply with the best-matching section of the Markdown knowledge base, as written."""

    def __init__(
        self,
        retriever: Retriever,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        max_chars: int = 600,
    ) -> None:
        self._retriever = retriever
        self._min_confidence = min_confidence
        self._max_chars = max_chars

    def answer(self, question: str) -> BackendAnswer | None:
        matches = self._retriever.search(question, limit=1)
        if not matches or matches[0].confidence < self._min_confidence:
            return None
        best = matches[0]
        return BackendAnswer(
            text=_trim(best.section.text, self._max_chars),
            source=best.section.label,
            confidence=round(best.confidence, 3),
        )


class RagApiBackend:
    """Delegate to a service that implements ``POST /ask``.

    The contract is the one of the companion repository ``rag-chatbot-with-citations``:
    the reply carries ``answer``, ``refused`` and ``citations``. A refusal there becomes
    a handoff here, so the member is never left with "I don't know".
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/", timeout=timeout, transport=transport
        )

    def answer(self, question: str) -> BackendAnswer | None:
        try:
            response = self._client.post("ask", json={"question": question})
        except httpx.HTTPError as exc:
            raise BackendError(f"RAG API unreachable ({type(exc).__name__})") from exc
        if response.status_code >= 400:
            raise BackendError(f"RAG API answered HTTP {response.status_code}")
        try:
            data = response.json()
            if data["refused"]:
                return None
            citations = data["citations"]
            labels = [
                f"{item['title']} > {item['heading']}" if item["heading"] else item["title"]
                for item in citations
            ]
            return BackendAnswer(
                text=data["answer"],
                source="; ".join(dict.fromkeys(labels)),
                confidence=max((item["score"] for item in citations), default=None),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise BackendError("RAG API answered in an unexpected shape") from exc
