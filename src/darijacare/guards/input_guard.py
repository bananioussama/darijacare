"""Input guard: sanitising, length limits, prompt-injection patterns and privacy masking.

Used by decision rule 1 ("entrée non conforme") and by the API before anything is
stored or logged. The guard never sends the raw text further:
:attr:`GuardResult.masked_text` is sanitised (no control or invisible characters, no
lone surrogates) and has phone numbers, URLs and e-mails replaced.

Injection patterns are matched on a folded copy of the text (NFKC, case folded,
whitespace collapsed), so that full-width letters, zero-width characters or extra
spaces do not hide a known pattern. The list stays short and explainable; it is a
first line of defence only: the MVP has no text generator, every reply comes from a
template or a fiche (cahier des charges, Tableau 33).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from darijacare.data.normalize import mask_pii

MODEL_PHONE_PLACEHOLDER = "06XXXXXXXX"


@dataclass(frozen=True)
class GuardResult:
    """Outcome of the input checks."""

    allowed: bool
    reason: str | None
    """``empty``, ``too_short``, ``too_long`` or ``injection`` when refused."""
    masked_text: str
    """Text with ``<TEL>``, ``<URL>``, ``<EMAIL>`` placeholders (safe to store and log)."""
    matched_pattern: str | None = None

    @property
    def model_text(self) -> str:
        """Text for the NLU model: ``<TEL>`` written as in the training data (``06XXXXXXXX``)."""
        return self.masked_text.replace("<TEL>", MODEL_PHONE_PLACEHOLDER)


KEPT_CONTROLS = frozenset({"\n", "\t"})


def sanitize(text: str) -> str:
    """Make any input safe to store, log and display.

    Lone surrogates (valid in JSON, refused by UTF-8 encoders) become ``?``; control
    characters (NUL, escape, bell…) become spaces, except new lines and tabs; invisible
    format characters (zero-width, bidirectional overrides, BOM) are removed.
    """
    text = text.encode("utf-8", "replace").decode("utf-8")
    out = []
    for ch in text:
        category = unicodedata.category(ch)
        if category == "Cf":
            continue
        out.append(" " if category == "Cc" and ch not in KEPT_CONTROLS else ch)
    return "".join(out)


def fold(text: str) -> str:
    """Folded copy used for pattern matching only (NFKC, case folded, single spaces)."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class InputGuard:
    """Configurable input checks (``configs/decision.yaml`` -> ``input``)."""

    def __init__(self, min_chars: int, max_chars: int, injection_patterns: Sequence[str]) -> None:
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.patterns = [re.compile(p, re.IGNORECASE) for p in injection_patterns]

    @classmethod
    def from_config(cls, cfg: Mapping[str, Any]) -> InputGuard:
        """Build from the ``input`` section of ``decision.yaml``."""
        return cls(cfg["min_chars"], cfg["max_chars"], cfg.get("injection_patterns", []))

    def check(self, text: str | None) -> GuardResult:
        """Check one message. Length is counted on the sanitised, stripped text."""
        raw = text if isinstance(text, str) else ""
        stripped = sanitize(raw).strip()
        masked = mask_pii(stripped)
        if not stripped:
            return GuardResult(False, "empty", masked)
        if len(stripped) < self.min_chars:
            return GuardResult(False, "too_short", masked)
        if len(stripped) > self.max_chars:
            return GuardResult(False, "too_long", masked)
        pattern = self.injection_pattern(stripped)
        if pattern is not None:
            return GuardResult(False, "injection", masked, pattern)
        return GuardResult(True, None, masked)

    def injection_pattern(self, text: str) -> str | None:
        """First injection pattern found in ``text`` (folded), or ``None``."""
        folded = fold(text)
        for pattern in self.patterns:
            if pattern.search(folded):
                return pattern.pattern
        return None
