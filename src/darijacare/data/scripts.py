"""Writing-script heuristics: Arabic script, Arabizi, or Darija mixed with French.

The coherence rules mirror the checks documented on the dataset card:

* ``arabizi``: no Arabic letters (and some Latin letters);
* ``arabic``: Arabic letters, and the text is not mostly Latin;
* ``mixed``: Latin letters and some French (or both scripts at once).

French is detected with a small lexicon of frequent function words and
telecom vocabulary, French elisions (``l'appli``, ``d'appel``) and accents.
This is a heuristic: Arabizi messages often contain French loanwords
(``connexion``, ``facture``), so the Arabizi/mixed boundary is fuzzy by nature.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ARABIC_LETTER_RE = re.compile(r"[ؠ-يٮ-ۓەۮۯۺ-ۼݐ-ݿࢠ-ࣿ" r"ﭐ-﷿ﹰ-﻿]")
LATIN_LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]")
FRENCH_ACCENT_RE = re.compile(r"[àâçéèêëîïôûùœ]", re.IGNORECASE)
FRENCH_ELISION_RE = re.compile(r"\b(?:l|d|j|n|s|c|qu|m|t)['’][a-zàâçéèêëîïôûùœ]", re.IGNORECASE)
LATIN_WORD_RE = re.compile(r"[a-zàâäçéèêëîïôöùûüÿœ]+", re.IGNORECASE)

FRENCH_WORDS: frozenset[str] = frozenset("""
    le la les un une des du de au aux et est sont pas ne je tu il elle nous vous ils
    mon ma mes ton ta son sa ses votre vos notre nos ce cet cette ces qui que quoi
    pour par avec sans dans sur sous mais ou donc car plus moins très tout tous
    toute rien depuis encore déjà aussi comme quand où si oui non merci bonjour
    bonsoir svp stp plait était avait fait suis ai été combien pourquoi comment
    possible mois jour jours semaine heure heures minute minutes facture factures
    recharge réseau problème connexion ligne abonnement forfait compte numéro client
    service agence offre paiement remboursement appel appels message messages carte
    puce téléphone portable fixe application appli app transfert messagerie vocale
    vocal activer activation migration fibre erreur technique technicien boite boîte
    signal alerte affichage commande garantie chargeur mise solde restant actuel
    disparu automatique notification frais contrat couverture montagne retard débit
    coupure panne vite consulter
    """.split())

Script = str  # "arabic" | "arabizi" | "mixed"


@dataclass(frozen=True)
class ScriptFeatures:
    """Character and lexical counts used by the script heuristics."""

    arabic_letters: int
    latin_letters: int
    french_markers: int

    @property
    def latin_ratio(self) -> float:
        """Share of Latin letters among all letters (0 when there are no letters)."""
        total = self.arabic_letters + self.latin_letters
        return self.latin_letters / total if total else 0.0


def script_features(text: str) -> ScriptFeatures:
    """Count Arabic letters, Latin letters and French markers in ``text``."""
    words = LATIN_WORD_RE.findall(text.lower())
    french = sum(1 for w in words if w in FRENCH_WORDS)
    french += len(FRENCH_ELISION_RE.findall(text))
    french += 1 if FRENCH_ACCENT_RE.search(text) else 0
    return ScriptFeatures(
        arabic_letters=len(ARABIC_LETTER_RE.findall(text)),
        latin_letters=len(LATIN_LETTER_RE.findall(text)),
        french_markers=french,
    )


def is_script_coherent(text: str, script: Script) -> bool:
    """Return ``True`` when ``text`` is consistent with its ``script`` label."""
    f = script_features(text)
    if script == "arabizi":
        return f.arabic_letters == 0 and f.latin_letters > 0
    if script == "arabic":
        return f.arabic_letters > 0 and f.latin_ratio <= 0.5
    if script == "mixed":
        return f.latin_letters > 0 and (f.arabic_letters > 0 or f.french_markers > 0)
    raise ValueError(f"Script inconnu : {script!r}")


def detect_script(text: str) -> Script:
    """Guess the script of an unlabelled message.

    Rules: no Latin letters -> ``arabic``; no Arabic letters -> ``mixed`` if at
    least two French markers, else ``arabizi``; both scripts -> ``mixed`` if any
    French marker or mostly Latin, else ``arabic``. Empty or letter-less text
    defaults to ``arabic``.
    """
    f = script_features(text)
    if f.latin_letters == 0:
        return "arabic"
    if f.arabic_letters == 0:
        return "mixed" if f.french_markers >= 2 else "arabizi"
    return "mixed" if f.french_markers >= 1 or f.latin_ratio > 0.5 else "arabic"
