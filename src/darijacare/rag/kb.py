"""Knowledge base of 75 fictional fiches, one per intent (cahier des charges, F-KB-01).

Each fiche is a Markdown file ``kb/<category>/<intent>.md`` with a YAML front
matter (``id, intent, category, version, status: fictif, langs``), a notice that
the content is fictional, then a French part and a Darija part (Arabic script),
each with five sections: objective, steps, conditions, limits, escalation.

The Markdown files are the source of truth (they are what the team reviews).
:func:`render_fiche` / :func:`parse_fiche` round-trip, and
:func:`generate_from_source` builds the initial files from ``kb/_source/*.yaml``
without overwriting reviewed files unless asked to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from darijacare.data.normalize import PHONE_RE
from darijacare.data.taxonomy import Taxonomy

LANGS = ("fr", "ar")
SECTION_KEYS = ("objet", "etapes", "conditions", "limites", "escalade")
LIST_SECTIONS = ("etapes", "conditions", "limites")
HEADINGS: dict[str, dict[str, str]] = {
    "fr": {
        "objet": "Objet",
        "etapes": "Étapes",
        "conditions": "Conditions",
        "limites": "Limites",
        "escalade": "Escalade",
    },
    "ar": {
        "objet": "الهدف",
        "etapes": "الخطوات",
        "conditions": "الشروط",
        "limites": "الحدود",
        "escalade": "التحويل لمستشار",
    },
}
LANG_TITLES = {"fr": "Version française", "ar": "النسخة بالدارجة"}
NOTICES = {
    "fr": "> ⚠️ **Fiche fictive** rédigée pour le projet académique DarijaCare. Elle ne décrit "
    "pas la procédure d'un opérateur réel et ne contient ni prix, ni numéro, ni engagement réels.",
    "ar": "> ⚠️ **بطاقة خيالية** مكتوبة للمشروع الجامعي DarijaCare. ما كتوصفش الإجراءات ديال "
    "شي أوبيراتور حقيقي، وما فيها لا أثمنة لا أرقام لا التزامات حقيقية.",
}


@dataclass
class Fiche:
    """One knowledge-base fiche."""

    intent: str
    category: str
    version: int
    status: str
    titles: dict[str, str]
    sections: dict[str, dict[str, Any]]
    """``sections[lang][key]``: str for objet/escalade, list[str] for the others."""
    reviewed_by: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"KB-{self.intent}"

    def text(self, lang: str, key: str) -> str:
        """Section content as plain text (lists joined with line breaks)."""
        value = self.sections[lang][key]
        return "\n".join(value) if isinstance(value, list) else str(value)

    def word_count(self, lang: str) -> int:
        return sum(len(self.text(lang, k).split()) for k in SECTION_KEYS)


# --- Markdown ----------------------------------------------------------------


def render_fiche(f: Fiche) -> str:
    """Render a fiche as Markdown with front matter."""
    front = {
        "id": f.id,
        "intent": f.intent,
        "category": f.category,
        "version": f.version,
        "status": f.status,
        "langs": list(LANGS),
        "reviewed_by": f.reviewed_by,
    }
    out = ["---", yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip(), "---", ""]
    for lang in LANGS:
        out += [f"# {LANG_TITLES[lang]} — {f.titles[lang]}", "", NOTICES[lang], ""]
        for key in SECTION_KEYS:
            out += [f"## {HEADINGS[lang][key]}", ""]
            value = f.sections[lang][key]
            if key == "etapes":
                out += [f"{i}. {v}" for i, v in enumerate(value, start=1)]
            elif key in LIST_SECTIONS:
                out += [f"- {v}" for v in value]
            else:
                out.append(str(value))
            out.append("")
    return "\n".join(out).rstrip() + "\n"


_FRONT_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_ITEM_RE = re.compile(r"^(?:\d+\.|-)\s+(.*)$")


def parse_fiche(text: str) -> Fiche:
    """Parse a Markdown fiche produced by :func:`render_fiche` (or edited by hand)."""
    m = _FRONT_RE.match(text)
    if not m:
        raise ValueError("Front matter YAML manquant")
    front = yaml.safe_load(m.group(1))
    body = text[m.end() :]
    titles: dict[str, str] = {}
    sections: dict[str, dict[str, Any]] = {lang: {} for lang in LANGS}
    lang: str | None = None
    key: str | None = None
    buf: list[str] = []
    heading_to_key = {lg: {v: k for k, v in HEADINGS[lg].items()} for lg in LANGS}

    def flush() -> None:
        if lang is None or key is None:
            return
        lines = [ln.strip() for ln in buf if ln.strip() and not ln.startswith(">")]
        if key in LIST_SECTIONS:
            items = [_ITEM_RE.match(ln) for ln in lines]
            sections[lang][key] = [it.group(1).strip() for it in items if it]
        else:
            sections[lang][key] = " ".join(lines)

    for line in body.splitlines():
        if line.startswith("# "):
            flush()
            key, buf = None, []
            header = line[2:]
            lang = next((lg for lg in LANGS if header.startswith(LANG_TITLES[lg])), None)
            if lang is None:
                raise ValueError(f"Titre de langue inconnu : {line!r}")
            titles[lang] = header.split(" — ", 1)[1].strip() if " — " in header else ""
        elif line.startswith("## "):
            flush()
            buf = []
            if lang is None:
                raise ValueError("Section avant le titre de langue")
            name = line[3:].strip()
            if name not in heading_to_key[lang]:
                raise ValueError(f"Section inconnue {name!r} ({lang})")
            key = heading_to_key[lang][name]
        else:
            buf.append(line)
    flush()
    return Fiche(
        intent=front["intent"],
        category=front["category"],
        version=int(front["version"]),
        status=str(front["status"]),
        titles=titles,
        sections=sections,
        reviewed_by=list(front.get("reviewed_by") or []),
    )


# --- Loading, validation, generation -----------------------------------------


def fiche_path(kb_dir: Path, category: str, intent: str) -> Path:
    return kb_dir / category / f"{intent}.md"


def load_kb(kb_dir: Path) -> dict[str, Fiche]:
    """Load every ``kb/<category>/<intent>.md`` fiche, keyed by intent."""
    fiches: dict[str, Fiche] = {}
    for path in sorted(kb_dir.glob("*/*.md")):
        f = parse_fiche(path.read_text(encoding="utf-8"))
        if f.intent in fiches:
            raise ValueError(f"Deux fiches pour l'intention {f.intent}")
        fiches[f.intent] = f
    return fiches


def validate_kb(
    fiches: dict[str, Fiche], taxonomy: Taxonomy, min_words: int = 150, max_words: int = 300
) -> list[str]:
    """Return a list of problems (empty when the knowledge base is valid).

    Checks: one fiche per taxonomy intent and no extra ones; category matches the
    taxonomy; status ``fictif``; all sections present and non-empty in both
    languages; total words (FR + AR) in ``[min_words, max_words]`` (Table 21:
    150–300 words per fiche); no phone number.
    """
    problems: list[str] = []
    i2c = taxonomy.intent_to_category
    for intent in sorted(set(i2c) - set(fiches)):
        problems.append(f"{intent} : fiche manquante")
    for intent in sorted(set(fiches) - set(i2c)):
        problems.append(f"{intent} : intention absente de la taxonomie")
    for intent, f in sorted(fiches.items()):
        if intent in i2c and f.category != i2c[intent]:
            problems.append(f"{intent} : catégorie {f.category} ≠ {i2c[intent]}")
        if f.status != "fictif":
            problems.append(f"{intent} : statut {f.status!r} (attendu « fictif »)")
        for lang in LANGS:
            if not f.titles.get(lang):
                problems.append(f"{intent} [{lang}] : titre manquant")
            for key in SECTION_KEYS:
                value = f.sections.get(lang, {}).get(key)
                if not value:
                    problems.append(f"{intent} [{lang}] : section {key} vide")
            if all(f.sections.get(lang, {}).get(k) for k in SECTION_KEYS):
                full = "\n".join(f.text(lang, k) for k in SECTION_KEYS)
                if PHONE_RE.search(full):
                    problems.append(f"{intent} [{lang}] : numéro de téléphone détecté")
        complete = all(f.sections.get(lg, {}).get(k) for lg in LANGS for k in SECTION_KEYS)
        if complete:
            n = sum(f.word_count(lg) for lg in LANGS)
            if not min_words <= n <= max_words:
                problems.append(f"{intent} : {n} mots (attendu {min_words}–{max_words})")
    return problems


def fiche_from_source(intent: str, category: str, src: dict[str, Any], version: int = 1) -> Fiche:
    """Build a fiche from one entry of ``kb/_source/<category>.yaml``."""
    sections = {lang: {key: src[f"{key}_{lang}"] for key in SECTION_KEYS} for lang in LANGS}
    return Fiche(
        intent,
        category,
        version,
        "fictif",
        {lang: src[f"title_{lang}"] for lang in LANGS},
        sections,
    )


def generate_from_source(kb_dir: Path, force: bool = False) -> list[Path]:
    """Write Markdown fiches from ``kb/_source``; existing files are kept unless ``force``."""
    written: list[Path] = []
    for src_file in sorted((kb_dir / "_source").glob("*.yaml")):
        category = src_file.stem
        data = yaml.safe_load(src_file.read_text(encoding="utf-8")) or {}
        for intent, entry in data.items():
            path = fiche_path(kb_dir, category, intent)
            if path.exists() and not force:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                render_fiche(fiche_from_source(intent, category, entry)),
                encoding="utf-8",
                newline="\n",
            )
            written.append(path)
    return written
