"""Text normalization shared by retrieval and by the analytics report."""

from __future__ import annotations

import re
import unicodedata

_WORD_RE = re.compile(r"[^\W_]+")

# Function words and chat filler that say nothing about the topic of a question.
# Question words such as "what" and "how" are listed on purpose: nearly every
# question has one, so they cannot help to tell two FAQ entries apart.
STOPWORDS = frozenset(
    """
    a about actually after again all also always am an and any anybody anyone anything are aren
    as ask asked asking at be because been before being but by can could couldn did didn do does
    doesn doing don during each else even ever everything for from get gets getting gm go going
    got guys had has have having he hello help her here hey hi him his how i if in into is isn it
    its just know let like ll maybe me might more most much must my need needs no not nothing now
    of off ok okay on once one only or other our out over please pls question questions quick re
    really same she should so some somebody someone something still such sure tell than thank
    thanks that the their them then there these they thing things this those though thx to too u
    under until up ur us use used using ve very want wants was wasn we wen were what when where
    which while who whom why will with won wonder wondering would wouldn yes yet you your yours
    """.split()  # noqa: SIM905 (a word list is easier to review as text than as 190 literals)
)

# "hi team," / "dear support," at the start of a message addresses someone; it is not the topic.
_SALUTATION_RE = re.compile(
    r"^\s*(?:hi|hey|hello|dear|gm|yo)\b[\s,!.]*"
    r"(?:(?:there|team|admins?|mods?|support|devs?|everyone|all|folks)\b[\s,!.:]*)?",
    re.IGNORECASE,
)

_SIBILANT_PLURALS = ("ches", "shes", "sses", "xes", "zes")
_VOWELS = frozenset("aeiouy")
_NATURAL_DOUBLES = frozenset("lsfz")  # "call", "pass", "staff", "buzz" keep their double letter


def stem(word: str) -> str:
    """Strip common English inflections so "fees", "bridging" and "staked" match their base form.

    This is a deliberately small suffix stripper, not a full Porter stemmer. It only
    has to make both sides of a comparison agree, so a stem does not need to be a
    real word ("bridge" and "bridging" both become "bridg").
    """
    word = _strip_plural(word)
    word = _strip_suffix(word)
    if len(word) >= 4 and word.endswith("e"):
        word = word[:-1]
    return word


def _strip_plural(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(_SIBILANT_PLURALS):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _strip_suffix(word: str) -> str:
    """Remove one of -ing, -ed or -able when a plausible base word is left."""
    for suffix, shortest_base in (("ing", 3), ("ed", 3), ("able", 4)):
        if not word.endswith(suffix):
            continue
        base = word[: -len(suffix)]
        is_eed_word = suffix == "ed" and base.endswith("e")  # "seed", "need", "speed"
        if len(base) < shortest_base or is_eed_word or not _VOWELS.intersection(base):
            return word
        doubled = base[-1] == base[-2] and base[-1] not in _VOWELS
        if len(base) >= 4 and doubled and base[-1] not in _NATURAL_DOUBLES:
            return base[:-1]  # "swapp" -> "swap"
        return base
    return word


def tokenize(text: str) -> list[str]:
    """Split text into lowercase stemmed terms, without stopwords and bare numbers."""
    return [
        stem(word)
        for word in _words(text)
        if len(word) > 1 and not word.isdigit() and word not in STOPWORDS
    ]


def question_terms(question: str) -> list[str]:
    """The distinct informative terms of a member's question, in order of appearance."""
    return list(dict.fromkeys(tokenize(strip_salutation(question))))


def strip_salutation(text: str) -> str:
    """Drop an opening such as "hi team," so the addressee is not mistaken for the topic."""
    return _SALUTATION_RE.sub("", text, count=1)


def normalize_question(text: str) -> str:
    """Readable canonical form of a question: lowercase words separated by single spaces."""
    return " ".join(_words(text))


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(unicodedata.normalize("NFKC", text).casefold())
