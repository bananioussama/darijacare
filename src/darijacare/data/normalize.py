"""Multi-script text normalisation (cahier des charges, F-DAT-03 and Table 19).

The original ``text`` is never modified: normalisation produces a new
``text_norm`` column. Every rule is a small pure function and can be switched
off from ``configs/data.yaml`` (``normalize.enabled: false`` gives the
"no normalisation" ablation, where only privacy masking stays on).

Rule order matters and is fixed:

1. Unicode NFKC (full-width forms, Arabic presentation forms);
2. Arabic-Indic digits -> ASCII (``٢٠`` -> ``20``) so numbers can be masked;
3. Arabic diacritics and tatweel removed;
4. alef variants (أ إ آ ٱ) -> ا, alef maqsura and Persian ya (ى ی) -> ي;
5. Arabic punctuation (، ؛ ؟) -> Latin equivalents;
6. Latin text lowercased;
7. URLs, e-mails and phone numbers masked as ``<URL>``, ``<EMAIL>``, ``<TEL>``;
8. letter elongation reduced (``saaaafi`` -> ``saafi``); ASCII digits are never
   touched, so Arabizi digits 2, 3, 5, 7, 9 and amounts are preserved;
9. whitespace collapsed.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

import pandas as pd

TEL_TOKEN = "<TEL>"
URL_TOKEN = "<URL>"
EMAIL_TOKEN = "<EMAIL>"

ARABIC_DIACRITICS_RE = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ]")
TATWEEL = "ـ"
ALEF_TABLE = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"})
YA_TABLE = str.maketrans({"ى": "ي", "ی": "ي"})
ARABIC_DIGITS_TABLE = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
ARABIC_PUNCT_TABLE = str.maketrans({"،": ",", "؛": ";", "؟": "?", "٪": "%"})

URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Moroccan numbers (0[5-7]..., +212 / 00212) and other international numbers
# (00 + country code), written with digits or with the dataset's X placeholders,
# optionally separated by spaces, dots or dashes. The look-behind only excludes
# Latin letters and digits, so a number glued to an Arabic word is still masked.
PHONE_RE = re.compile(
    r"(?<![0-9A-Za-z+<])"
    r"(?:"
    r"(?:\+|00)212[\s.-]?0?[5-7](?:[\s.-]?[0-9xX]){8}"  # +212 6 12 34 56 78
    r"|0[5-7](?:[\s.-]?[0-9xX]){8}"  # 06 12 34 56 78 / 06XXXXXXXX
    r"|(?:\+|00)[1-9][0-9]{0,2}(?:[\s.-]?[0-9xX]){6,12}"  # +33 6..., 0034XXXXXX
    r")"
    r"(?![0-9A-Za-z])"
)
WHITESPACE_RE = re.compile(r"\s+")


def _elongation_re(max_repeat: int) -> re.Pattern[str]:
    """Match a letter (never a digit or space) repeated more than ``max_repeat`` times."""
    return re.compile(r"([^\W\d_])\1{" + str(max_repeat) + ",}")


@dataclass(frozen=True)
class NormalizerConfig:
    """Switches for each normalisation rule (all on by default)."""

    enabled: bool = True
    nfkc: bool = True
    arabic_diacritics: bool = True
    tatweel: bool = True
    unify_alef: bool = True
    unify_ya: bool = True
    arabic_indic_digits: bool = True
    arabic_punctuation: bool = True
    lowercase_latin: bool = True
    reduce_elongation: bool = True
    max_repeat: int = 2
    mask_urls: bool = True
    mask_emails: bool = True
    mask_phones: bool = True

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> NormalizerConfig:
        """Build a config from a YAML mapping, ignoring unknown keys."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


# --- Individual rules -------------------------------------------------------


def nfkc(text: str) -> str:
    """Apply Unicode NFKC normalisation."""
    return unicodedata.normalize("NFKC", text)


def remove_arabic_diacritics(text: str) -> str:
    """Remove Arabic harakat, shadda, sukun, superscript alef and Quranic marks."""
    return ARABIC_DIACRITICS_RE.sub("", text)


def remove_tatweel(text: str) -> str:
    """Remove the Arabic elongation character (tatweel, U+0640)."""
    return text.replace(TATWEEL, "")


def unify_alef(text: str) -> str:
    """Map أ إ آ ٱ to bare alef ا."""
    return text.translate(ALEF_TABLE)


def unify_ya(text: str) -> str:
    """Map alef maqsura ى and Persian ya ی to ي."""
    return text.translate(YA_TABLE)


def arabic_indic_digits_to_ascii(text: str) -> str:
    """Convert Arabic-Indic and Persian digits to ASCII digits."""
    return text.translate(ARABIC_DIGITS_TABLE)


def arabic_punctuation_to_latin(text: str) -> str:
    """Convert Arabic comma, semicolon, question mark and percent to Latin ones."""
    return text.translate(ARABIC_PUNCT_TABLE)


_TOKEN_RESTORE_RE = re.compile(r"<(tel|url|email)>")


def lowercase_latin(text: str) -> str:
    """Lowercase the text (Arabic script has no case, so only Latin letters change).

    Masking tokens (``<TEL>``, ``<URL>``, ``<EMAIL>``) keep their case, so
    normalising an already-masked text is idempotent.
    """
    return _TOKEN_RESTORE_RE.sub(lambda m: m.group(0).upper(), text.lower())


def mask_urls(text: str) -> str:
    """Replace URLs with ``<URL>``."""
    return URL_RE.sub(URL_TOKEN, text)


def mask_emails(text: str) -> str:
    """Replace e-mail addresses with ``<EMAIL>``."""
    return EMAIL_RE.sub(EMAIL_TOKEN, text)


def mask_phones(text: str) -> str:
    """Replace phone numbers (real digits or ``06XXXXXXXX`` placeholders) with ``<TEL>``."""
    return PHONE_RE.sub(TEL_TOKEN, text)


def reduce_elongation(text: str, max_repeat: int = 2) -> str:
    """Shorten runs of the same letter to ``max_repeat`` characters.

    Digits are never shortened (``3`` in ``3lach`` or ``1000`` dirhams stay intact).
    """
    return _elongation_re(max_repeat).sub(lambda m: m.group(1) * max_repeat, text)


def collapse_whitespace(text: str) -> str:
    """Collapse whitespace runs to one space and strip the ends."""
    return WHITESPACE_RE.sub(" ", text).strip()


def mask_pii(text: str) -> str:
    """Mask URLs, e-mails and phone numbers only (privacy guard, always safe to apply)."""
    return mask_phones(mask_emails(mask_urls(text)))


# --- Pipeline ---------------------------------------------------------------


class Normalizer:
    """Apply the configured rules in the documented order."""

    def __init__(self, config: NormalizerConfig | None = None) -> None:
        self.config = config or NormalizerConfig()

    def __call__(self, text: str) -> str:
        """Normalise one message. Non-string input is treated as an empty string."""
        if not isinstance(text, str):
            return ""
        c = self.config
        if not c.enabled:
            # Ablation: raw text, but privacy masking is never disabled.
            return collapse_whitespace(mask_pii(text))
        if c.nfkc:
            text = nfkc(text)
        if c.arabic_indic_digits:
            text = arabic_indic_digits_to_ascii(text)
        if c.arabic_diacritics:
            text = remove_arabic_diacritics(text)
        if c.tatweel:
            text = remove_tatweel(text)
        if c.unify_alef:
            text = unify_alef(text)
        if c.unify_ya:
            text = unify_ya(text)
        if c.arabic_punctuation:
            text = arabic_punctuation_to_latin(text)
        if c.lowercase_latin:
            text = lowercase_latin(text)
        if c.mask_urls:
            text = mask_urls(text)
        if c.mask_emails:
            text = mask_emails(text)
        if c.mask_phones:
            text = mask_phones(text)
        if c.reduce_elongation:
            text = reduce_elongation(text, c.max_repeat)
        return collapse_whitespace(text)


def normalize_text(text: str, config: NormalizerConfig | None = None) -> str:
    """Normalise a single message with ``config`` (default: every rule on)."""
    return Normalizer(config)(text)


def add_normalized_column(
    df: pd.DataFrame, config: NormalizerConfig | None = None, column: str = "text_norm"
) -> pd.DataFrame:
    """Return a copy of ``df`` with ``column`` inserted right after ``text``."""
    norm = Normalizer(config)
    out = df.copy()
    values = out["text"].map(norm)
    if column in out.columns:
        out[column] = values
    else:
        out.insert(list(out.columns).index("text") + 1, column, values)
    return out


def run_normalize(paths: Any, config: Mapping[str, Any]) -> dict[str, Any]:
    """Pipeline stage: add ``text_norm`` to the validated splits.

    Reads ``data/interim/validated/{split}.jsonl`` and writes
    ``data/interim/normalized/{split}.jsonl`` plus ``reports/normalize/report.json``.
    """
    from darijacare.io import read_jsonl, write_json, write_jsonl

    cfg = NormalizerConfig.from_mapping(config["normalize"])
    report: dict[str, Any] = {"config": {f.name: getattr(cfg, f.name) for f in fields(cfg)}}
    for split in ("train", "test"):
        df = read_jsonl(paths.interim / "validated" / f"{split}.jsonl")
        out = add_normalized_column(df, cfg)
        write_jsonl(out, paths.interim / "normalized" / f"{split}.jsonl")
        report[split] = {
            "rows": len(out),
            "changed": int((out["text"] != out["text_norm"]).sum()),
            "tel_masked_rows": int(out["text_norm"].str.contains(TEL_TOKEN, regex=False).sum()),
            "url_masked_rows": int(out["text_norm"].str.contains(URL_TOKEN, regex=False).sum()),
            "empty_after_normalization": int((out["text_norm"].str.len() == 0).sum()),
        }
    write_json(report, paths.reports / "normalize" / "report.json")
    return report
