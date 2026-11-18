"""Input guard: length limits, prompt-injection patterns and privacy masking.

Used by decision rule 1 ("entrée non conforme") and, in Phase 4, by the API
before anything is stored or logged. The guard never sends the raw text further:
:attr:`GuardResult.masked_text` has phone numbers, URLs and e-mails replaced.
"""

from __future__ import annotations

import re
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
        """Check one message. Length is counted on the stripped text."""
        raw = text if isinstance(text, str) else ""
        stripped = raw.strip()
        masked = mask_pii(stripped)
        if not stripped:
            return GuardResult(False, "empty", masked)
        if len(stripped) < self.min_chars:
            return GuardResult(False, "too_short", masked)
        if len(stripped) > self.max_chars:
            return GuardResult(False, "too_long", masked)
        for pattern in self.patterns:
            if pattern.search(stripped):
                return GuardResult(False, "injection", masked, pattern.pattern)
        return GuardResult(True, None, masked)
