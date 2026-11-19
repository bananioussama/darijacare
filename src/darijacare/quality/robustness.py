"""Perturbation test of the NLU (F-NLU-07, Tableau 33: « baisse de F1 mesurée »).

Each message of a labelled split is perturbed in a reproducible way (one random
generator per message, seeded by the global seed, the perturbation and the message
id), then goes through the production path: input sanitising and masking
(:meth:`InputGuard.check`, ``model_text``) and the served model. The intent F1 macro
is compared with the unperturbed predictions. Target (cahier des charges, Tableau 36):
a drop of at most 5 points.

Perturbations (rates fixed a priori, never tuned on the test set):

* ``fautes``: typing errors in about 15 % of the words (swap, deletion, doubling,
  neighbouring key or confusable Arabic letter), at least one per message;
* ``translitteration``: other spellings of the same words: Arabizi digits written as
  letters (3 -> a, 7 -> h, 9 -> q…), ch/sh, French accents dropped, Arabic alef,
  ta marbuta and final ya variants;
* ``caracteres_exotiques``: two of elongation, tatweel, diacritics, emojis, repeated
  punctuation, capitals, Arabic-Indic digits, zero-width characters, full-width letters;
* ``brievete``: only the first half of the words (at least two);
* ``mixte``: one of the first three, drawn per message.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Callable
from typing import Any

import pandas as pd

from darijacare.guards.input_guard import InputGuard
from darijacare.nlu.metrics import headline_metrics

KINDS: tuple[str, ...] = (
    "fautes",
    "translitteration",
    "caracteres_exotiques",
    "brievete",
    "mixte",
)
TYPO_RATE = 0.15
VARIANT_RATE = 0.5
BREVITY_KEEP = 0.5

PROTECTED_RE = re.compile(r"X{3,}|<[A-Z]+>|\d{4,}")
"""Masked placeholders and long numbers are never changed."""
LETTER_RE = re.compile(r"[^\W\d_]")
ARABIC_RE = re.compile(r"[ء-ي]")
LATIN_RE = re.compile(r"[a-zA-Z]")

AZERTY_NEIGHBOURS = {
    "a": "zq", "z": "aes", "e": "zrd", "r": "etf", "t": "ryg", "y": "tuh", "u": "yij",
    "i": "uok", "o": "ipl", "p": "om", "q": "asw", "s": "qdz", "d": "sfe", "f": "dgr",
    "g": "fht", "h": "gjy", "j": "hku", "k": "jli", "l": "kmo", "m": "lp", "w": "xq",
    "x": "wcs", "c": "xvd", "v": "cbf", "b": "vng", "n": "bh",
}  # fmt: skip
ARABIC_CONFUSABLE = {
    "ت": "ث", "ث": "ت", "ح": "خ", "خ": "ح", "د": "ذ", "ذ": "د", "س": "ش", "ش": "س",
    "ص": "ض", "ض": "ص", "ط": "ظ", "ظ": "ط", "ع": "غ", "غ": "ع", "ق": "ف", "ف": "ق",
    "ر": "ز", "ز": "ر", "ه": "ة", "ة": "ه", "ي": "ى", "ى": "ي",
}  # fmt: skip
ARABIZI_DIGITS = {"3": "a", "7": "h", "9": "q", "2": "a", "5": "kh", "8": "gh"}
LATIN_VARIANTS = (("ch", "sh"), ("ou", "u"), ("é", "e"), ("è", "e"), ("à", "a"), ("ç", "c"))
DIACRITICS = "َُِّْ"
TATWEEL = "ـ"
EMOJIS = ("😡", "🙏", "😭", "📱", "💸", "‼️", "🤔")
ARABIC_INDIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def _eligible(word: str) -> bool:
    return bool(LETTER_RE.search(word)) and not PROTECTED_RE.search(word)


def _typo(word: str, rng: random.Random) -> str:
    """One typing error in ``word`` (at least three characters)."""
    i = rng.randrange(len(word))
    op = rng.choice(("swap", "delete", "double", "neighbour"))
    if op == "swap" and i < len(word) - 1:
        return word[:i] + word[i + 1] + word[i] + word[i + 2 :]
    if op == "double":
        return word[:i] + word[i] + word[i:]
    if op == "neighbour":
        repl = AZERTY_NEIGHBOURS.get(word[i].lower()) or ARABIC_CONFUSABLE.get(word[i])
        if repl:
            return word[:i] + rng.choice(repl) + word[i + 1 :]
    return word[:i] + word[i + 1 :]


def typos(text: str, rng: random.Random) -> str:
    """Typing errors in about :data:`TYPO_RATE` of the words, at least one."""
    words = text.split(" ")
    candidates = [i for i, w in enumerate(words) if len(w) >= 3 and _eligible(w)]
    if not candidates:
        return text
    chosen = [i for i in candidates if rng.random() < TYPO_RATE] or [rng.choice(candidates)]
    for i in chosen:
        words[i] = _typo(words[i], rng)
    return " ".join(words)


def _digit_as_letter(word: str, rng: random.Random) -> str:
    """Arabizi digits between letters written as letters (``m3ak`` -> ``maak``)."""
    out = []
    for i, ch in enumerate(word):
        prev_ok = i == 0 or LATIN_RE.match(word[i - 1]) is not None
        next_ok = i == len(word) - 1 or LATIN_RE.match(word[i + 1]) is not None
        has_letter = (i > 0 and LATIN_RE.match(word[i - 1])) or (
            i < len(word) - 1 and LATIN_RE.match(word[i + 1])
        )
        eligible = ch in ARABIZI_DIGITS and prev_ok and next_ok and has_letter
        if eligible and rng.random() < VARIANT_RATE:
            out.append(ARABIZI_DIGITS[ch])
            continue
        out.append(ch)
    return "".join(out)


def _arabic_variants(word: str, rng: random.Random) -> str:
    chars = list(word)
    if chars and chars[0] == "ا" and rng.random() < 0.3:
        chars[0] = rng.choice("أإ")
    chars = ["ا" if c in "أإآ" and rng.random() < VARIANT_RATE else c for c in chars]
    if chars and chars[-1] in "ةيى" and rng.random() < VARIANT_RATE:
        chars[-1] = {"ة": "ه", "ي": "ى", "ى": "ي"}[chars[-1]]
    return "".join(chars)


def transliteration(text: str, rng: random.Random) -> str:
    """Other spellings of the same words (Arabizi digits, ch/sh, accents, alef…)."""
    words = text.split(" ")
    for i, w in enumerate(words):
        if not _eligible(w):
            continue
        if ARABIC_RE.search(w):
            words[i] = _arabic_variants(w, rng)
            continue
        w = _digit_as_letter(w, rng)
        for a, b in LATIN_VARIANTS:
            if a in w and rng.random() < VARIANT_RATE:
                w = w.replace(a, b)
        words[i] = w
    out = " ".join(words)
    return out if out != text else _force_variant(text)


def _force_variant(text: str) -> str:
    """Fallback when no random change happened: first applicable spelling change
    (digits are left alone here, so that amounts such as ``30dh`` stay intact)."""
    for a, b in (*LATIN_VARIANTS, ("أ", "ا"), ("إ", "ا"), ("ة", "ه"), ("ى", "ي")):
        if a in text:
            return text.replace(a, b, 1)
    return text


def _exotic_op(text: str, op: str, rng: random.Random) -> str:
    words = text.split(" ")
    eligible = [i for i, w in enumerate(words) if _eligible(w) and len(w) >= 2]
    arabic = [i for i in eligible if ARABIC_RE.search(words[i])]
    latin = [i for i in eligible if LATIN_RE.search(words[i])]
    if op == "elongation" and eligible:
        i = rng.choice(eligible)
        w = words[i]
        j = rng.randrange(len(w))
        words[i] = w[: j + 1] + w[j] * 3 + w[j + 1 :]
    elif op == "tatweel" and arabic:
        i = rng.choice(arabic)
        w = words[i]
        words[i] = w[:1] + TATWEEL + w[1:]
    elif op == "diacritics" and arabic:
        i = rng.choice(arabic)
        words[i] = "".join(
            c + rng.choice(DIACRITICS) if ARABIC_RE.match(c) else c for c in words[i]
        )
    elif op == "capitals" and latin:
        i = rng.choice(latin)
        words[i] = words[i].upper()
    elif op == "zero_width" and eligible:
        i = rng.choice(eligible)
        w = words[i]
        words[i] = w[:1] + "​" + w[1:]
    elif op == "fullwidth" and latin:
        i = rng.choice(latin)
        words[i] = "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in words[i])
    elif op == "arabic_digits" and re.search(r"\d", text):
        return text.translate(ARABIC_INDIC)
    elif op == "emoji":
        return text + " " + "".join(rng.choice(EMOJIS) for _ in range(rng.randint(1, 3)))
    elif op == "punctuation":
        return text + rng.choice(("!!!", "???", "؟؟", "..."))
    else:
        return text + " " + rng.choice(EMOJIS)
    return " ".join(words)


EXOTIC_OPS = (
    "elongation",
    "tatweel",
    "diacritics",
    "capitals",
    "zero_width",
    "fullwidth",
    "arabic_digits",
    "emoji",
    "punctuation",
)


def exotic(text: str, rng: random.Random) -> str:
    """Two exotic-character changes drawn from :data:`EXOTIC_OPS`."""
    for op in rng.sample(EXOTIC_OPS, 2):
        text = _exotic_op(text, op, rng)
    return text


def brevity(text: str, rng: random.Random) -> str:
    """Keep only the first half of the words (at least two)."""
    words = text.split()
    if len(words) <= 2:
        return text
    return " ".join(words[: max(2, math.ceil(len(words) * BREVITY_KEEP))])


def mixed(text: str, rng: random.Random) -> str:
    """One of typos, transliteration or exotic characters, drawn per message."""
    return rng.choice((typos, transliteration, exotic))(text, rng)


PERTURB: dict[str, Callable[[str, random.Random], str]] = {
    "fautes": typos,
    "translitteration": transliteration,
    "caracteres_exotiques": exotic,
    "brievete": brevity,
    "mixte": mixed,
}


def perturb_texts(df: pd.DataFrame, kind: str, seed: int) -> list[str]:
    """Perturbed text of every row (reproducible: one generator per message)."""
    fn = PERTURB[kind]
    rows = zip(df["text"], df["id"], strict=True)
    return [fn(str(t), random.Random(f"{seed}:{kind}:{i}")) for t, i in rows]


def production_text(guard: InputGuard, text: str) -> str:
    """What the API gives the model: sanitised, masked (``model_text``)."""
    return guard.check(text).model_text


def summary(gold: pd.DataFrame, pred: pd.DataFrame) -> dict[str, float]:
    """Intent F1 macro and accuracy (end to end), category and needs_human accuracy."""
    m = headline_metrics(gold.reset_index(drop=True), pred.reset_index(drop=True))
    return {
        "intent_f1_macro": round(m["intent_f1_macro"], 4),
        "intent_end_to_end": round(m["intent_end_to_end"], 4),
        "category_acc": round(m["category_acc"], 4),
        "needs_human_acc": round(m["needs_human_acc"], 4),
    }


def compare(
    gold: pd.DataFrame,
    reference: pd.DataFrame,
    perturbed: dict[str, tuple[list[str], pd.DataFrame]],
    max_drop_points: float = 5.0,
) -> dict[str, Any]:
    """Metrics before / after each perturbation, overall and by script."""
    base = summary(gold, reference)
    report: dict[str, Any] = {"reference": base, "perturbations": {}}
    for kind, (texts, pred) in perturbed.items():
        after = summary(gold, pred)
        drop = round(100 * (base["intent_f1_macro"] - after["intent_f1_macro"]), 2)
        by_script = {}
        for script, idx in gold.groupby("script").groups.items():
            rows = gold.index.get_indexer(idx)
            b = summary(gold.iloc[rows], reference.iloc[rows])["intent_f1_macro"]
            a = summary(gold.iloc[rows], pred.iloc[rows])["intent_f1_macro"]
            by_script[str(script)] = {
                "avant": b,
                "apres": a,
                "baisse_points": round(100 * (b - a), 2),
            }
        changed = sum(t != o for t, o in zip(texts, gold["text"], strict=True))
        report["perturbations"][kind] = {
            **after,
            "baisse_f1_points": drop,
            "cible_atteinte": drop <= max_drop_points,
            "messages_modifies": round(changed / len(texts), 4),
            "par_ecriture": by_script,
        }
    return report
