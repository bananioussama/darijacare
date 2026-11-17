"""Unit tests for multi-script normalisation (one test per rule + pipeline)."""

from __future__ import annotations

import pandas as pd
import pytest

from darijacare.data.normalize import (
    Normalizer,
    NormalizerConfig,
    add_normalized_column,
    arabic_indic_digits_to_ascii,
    arabic_punctuation_to_latin,
    collapse_whitespace,
    mask_emails,
    mask_phones,
    mask_urls,
    nfkc,
    normalize_text,
    reduce_elongation,
    remove_arabic_diacritics,
    remove_tatweel,
    unify_alef,
    unify_ya,
)

# --- Individual rules --------------------------------------------------------


def test_nfkc_fullwidth_and_presentation_forms() -> None:
    assert nfkc("ｓａｌａｍ") == "salam"
    # Arabic presentation form (lam-alef ligature) -> base letters.
    assert nfkc("ﻻ") == "لا"


def test_remove_arabic_diacritics() -> None:
    assert remove_arabic_diacritics("بْغِيتْ نْشَارْجِي") == "بغيت نشارجي"
    assert remove_arabic_diacritics("نفعّل") == "نفعل"  # shadda
    assert remove_arabic_diacritics("3lach ma kaykhdemch") == "3lach ma kaykhdemch"


def test_remove_tatweel() -> None:
    assert remove_tatweel("شكـــرا") == "شكرا"


def test_unify_alef() -> None:
    assert unify_alef("أنا إلى آخر ٱلخط") == "انا الى اخر الخط"


def test_unify_ya() -> None:
    assert unify_ya("على مشى") == "علي مشي"
    assert unify_ya("فی") == "في"  # Persian ya


def test_arabic_indic_digits() -> None:
    assert arabic_indic_digits_to_ascii("خلصت ٢٠٠ درهم") == "خلصت 200 درهم"
    assert arabic_indic_digits_to_ascii("۵۰ dh") == "50 dh"


def test_arabic_punctuation() -> None:
    assert arabic_punctuation_to_latin("واش كاين، شي حل؟") == "واش كاين, شي حل?"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("saaaafi", "saafi"),
        ("bzaaaaaf", "bzaaf"),
        ("بزااااف", "بزااف"),
        ("merciiii", "mercii"),
        ("cool", "cool"),  # double letters are kept
    ],
)
def test_reduce_elongation(text: str, expected: str) -> None:
    assert reduce_elongation(text) == expected


@pytest.mark.parametrize(
    "text",
    ["3lach", "n9der", "7ta", "5edma", "ch7al b9a?", "2iyam", "1000 dh", "06 666 999"],
)
def test_arabizi_digits_and_amounts_are_kept(text: str) -> None:
    assert reduce_elongation(text) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3iyet l 06XXXXXXXX w ma jawbch", "3iyet l <TEL> w ma jawbch"),
        ("nmra dyali 0612345678.", "nmra dyali <TEL>."),
        ("06 12 34 56 78", "<TEL>"),
        ("06.12.34.56.78", "<TEL>"),
        ("+212 6 12 34 56 78", "<TEL>"),
        ("+212612345678", "<TEL>"),
        ("00212612345678", "<TEL>"),
        ("05XXXXXXXX،", "<TEL>،"),
        ("النمرة06XXXXXXXX", "النمرة<TEL>"),  # glued to an Arabic word
        ("rqm khoya f spain 0034XXXXXX", "rqm khoya f spain <TEL>"),
        ("06xxxxxxxx", "<TEL>"),
    ],
)
def test_mask_phones(text: str, expected: str) -> None:
    assert mask_phones(text) == expected


@pytest.mark.parametrize(
    "text",
    ["chargit 100 dh", "pass 20Go b 50 dh", "le 12/05/2026", "code 1234", "2000 dirhams"],
)
def test_mask_phones_keeps_amounts_and_dates(text: str) -> None:
    assert mask_phones(text) == text


def test_mask_urls_and_emails() -> None:
    assert mask_urls("chouf https://exemple.ma/offre?id=3 daba") == "chouf <URL> daba"
    assert mask_urls("www.exemple.com") == "<URL>"
    assert mask_emails("sifet l client@exemple.com") == "sifet l <EMAIL>"


def test_collapse_whitespace() -> None:
    assert collapse_whitespace("  salam \n\t  khoya  ") == "salam khoya"


# --- Full pipeline -----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Arabic script
        ("أنا بْغِيت نشارجـــي ٥٠ درهم، واش ممكن؟", "انا بغيت نشارجي 50 درهم, واش ممكن?"),
        # Arabizi: digits kept, case lowered, elongation reduced
        ("Salaaaam, 3LACH ma n9derch ndkhel?", "salaam, 3lach ma n9derch ndkhel?"),
        # Mixed Darija + French, with a masked number
        ("Bghit n3ref la FACTURE dyal 06XXXXXXXX", "bghit n3ref la facture dyal <TEL>"),
        ("l'appli كيبقى غير كيدور", "l'appli كيبقي غير كيدور"),
    ],
)
def test_pipeline_examples(text: str, expected: str) -> None:
    assert normalize_text(text) == expected


def test_placeholder_tokens_keep_their_case() -> None:
    out = normalize_text("Ana f WWW.EXEMPLE.MA o nmra 0612345678")
    assert out == "ana f <URL> o nmra <TEL>"


def test_normalization_is_idempotent() -> None:
    samples = [
        "أنا بْغِيت نشارجـــي ٥٠ درهم، واش ممكن؟",
        "Salaaaam, 3LACH ma n9derch?",
        "Bghit la FACTURE dyal 06XXXXXXXX",
    ]
    for s in samples:
        once = normalize_text(s)
        assert normalize_text(once) == once


def test_normalization_is_deterministic() -> None:
    s = "Wach kayn chi PROMO f ramadan؟ 😀😀😀😀"
    assert normalize_text(s) == normalize_text(s)


def test_disabled_config_only_masks() -> None:
    cfg = NormalizerConfig(enabled=False)
    assert normalize_text("Salaaaam  أنا 06XXXXXXXX", cfg) == "Salaaaam أنا <TEL>"


def test_individual_switch() -> None:
    cfg = NormalizerConfig(lowercase_latin=False)
    assert normalize_text("FACTURE", cfg) == "FACTURE"


def test_from_mapping_ignores_unknown_keys() -> None:
    cfg = NormalizerConfig.from_mapping({"enabled": True, "max_repeat": 3, "unknown": 1})
    assert cfg.max_repeat == 3


@pytest.mark.parametrize("value", ["", "   ", None, 12])
def test_robust_to_empty_and_non_string(value: object) -> None:
    assert Normalizer()(value) == ""  # type: ignore[arg-type]


def test_add_normalized_column_keeps_original() -> None:
    df = pd.DataFrame({"id": ["a"], "text": ["Salaaaam"], "intent": ["greeting_thanks"]})
    out = add_normalized_column(df)
    assert list(out.columns) == ["id", "text", "text_norm", "intent"]
    assert out.loc[0, "text"] == "Salaaaam"
    assert out.loc[0, "text_norm"] == "salaam"
    assert "text_norm" not in df.columns  # input untouched
