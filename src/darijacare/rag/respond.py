"""Reply rendering with Jinja2 templates adapted to the customer's script (F-KB-04).

* One template per action and script (``templates/<script>/<action>.j2``), filled
  with the fiche of the intent; an intent can override the answer template with
  ``templates/<script>/intents/<intent>.j2`` (no override is needed today).
* The reply uses the fiche part written in the customer's script: Arabic script ->
  Darija in Arabic script; Arabizi -> Darija in Latin script (written by hand, not
  transliterated automatically); mixed -> French, framed with Darija formulas.
* Every factual sentence comes from the fiche: the answer opens with the fiche
  title (customer-facing) and lists its steps; the template only adds greetings,
  connecting words and the offer of an advisor (a capability of the assistant,
  not a claim about the procedure). Answers cite the fiche id and version.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from darijacare.decision.policy import Action, Decision
from darijacare.rag.kb import Fiche

TEMPLATE_DIR = Path(__file__).parent / "templates"
SCRIPTS = ("arabic", "arabizi", "mixed")
CONTENT_LANG = {"arabic": "ar", "arabizi": "arabizi", "mixed": "fr"}


@dataclass(frozen=True)
class RenderedReply:
    """Text sent to the customer and the fiches it relies on."""

    text: str
    template: str
    sources: list[dict[str, Any]]


def fiche_view(f: Fiche, lang: str) -> dict[str, Any]:
    """Fields of a fiche in one language, as used by the templates."""
    return {
        "id": f.id,
        "version": f.version,
        "title": f.titles[lang],
        "objet": f.sections[lang]["objet"],
        "etapes": list(f.sections[lang]["etapes"]),
        "escalade": f.sections[lang]["escalade"],
    }


class Responder:
    """Choose and fill the template for a decision."""

    def __init__(
        self, fiches: Mapping[str, Fiche], max_chars: int = 500, template_dir: Path = TEMPLATE_DIR
    ) -> None:
        self.fiches = dict(fiches)
        self.max_chars = max_chars
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=True,
            keep_trailing_newline=False,
        )

    def _render(self, script: str, name: str, **ctx: Any) -> str:
        script = script if script in SCRIPTS else "mixed"
        text = self.env.get_template(f"{script}/{name}.j2").render(**ctx)
        return "\n".join(line.rstrip() for line in text.strip().splitlines())

    def answer_template(self, script: str, intent: str) -> str:
        """Per-intent override ``<script>/intents/<intent>.j2`` if present, else ``answer``."""
        script = script if script in SCRIPTS else "mixed"
        override = f"intents/{intent}"
        if f"{script}/{override}.j2" in self.env.list_templates():
            return override
        return "answer"

    def render(
        self,
        decision: Decision,
        script: str,
        intent: str | None = None,
        fiche_intent: str | None = None,
    ) -> RenderedReply:
        """Render the reply for ``decision``.

        Args:
            decision: output of the policy.
            script: ``arabic``, ``arabizi`` or ``mixed`` (customer's writing).
            intent: predicted intent (used for direct templates and safety steps).
            fiche_intent: intent of the fiche chosen by retrieval (rule 7); ``None``
                when retrieval found no reliable fiche.
        """
        lang = CONTENT_LANG.get(script, "fr")
        a = decision.action
        if a is Action.REFUSE:
            return RenderedReply(
                self._render(
                    script, "refuse", reason=decision.refusal_reason, max_chars=self.max_chars
                ),
                "refuse",
                [],
            )
        if a is Action.OUT_OF_SCOPE:
            return RenderedReply(self._render(script, "out_of_scope"), "out_of_scope", [])
        if a is Action.CLARIFY:
            titles = [
                self.fiches[o].titles[lang] if o in self.fiches else o
                for o in decision.clarification_options[:2]
            ]
            return RenderedReply(self._render(script, "clarify", options=titles), "clarify", [])
        if a in (Action.ESCALATE, Action.SAFETY_ESCALATE):
            safety = decision.include_safety_procedure and intent in self.fiches
            fiche = fiche_view(self.fiches[intent], lang) if safety and intent else None
            level = decision.priority.level if decision.priority else None
            text = self._render(script, "escalate", fiche=fiche, safety=safety, priority=level)
            sources = [{"id": fiche["id"], "version": fiche["version"]}] if fiche else []
            return RenderedReply(text, "escalate", sources)
        if a is Action.TEMPLATE and intent == "greeting_thanks":
            return RenderedReply(self._render(script, "greeting"), "greeting", [])
        target = intent if a is Action.TEMPLATE else fiche_intent
        if target is None or target not in self.fiches:
            return RenderedReply(self._render(script, "no_source"), "no_source", [])
        fiche = fiche_view(self.fiches[target], lang)
        return RenderedReply(
            self._render(script, self.answer_template(script, target), fiche=fiche),
            "answer",
            [{"id": fiche["id"], "version": fiche["version"]}],
        )
