"""End-to-end message handling: guard -> NLU -> decision -> retrieval -> reply.

This is the single entry point the API (Phase 4) calls. Components are injected,
so tests can use fakes and the API can share loaded models between requests.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from darijacare.data.scripts import detect_script
from darijacare.decision.policy import Action, ConversationState, Decision, DecisionPolicy
from darijacare.guards.input_guard import InputGuard
from darijacare.nlu.service import NLUResult, NLUService
from darijacare.rag.respond import Responder
from darijacare.rag.retrieve import RetrievalResult, Retriever

log = logging.getLogger("darijacare.pipeline")


@dataclass
class AssistantReply:
    """Everything produced for one customer message (stored and shown in the UI)."""

    text: str
    """Reply sent to the customer."""
    masked_input: str
    """Customer message with phone numbers / URLs / e-mails masked (safe to store)."""
    script: str
    decision: Decision
    nlu: NLUResult | None
    retrieval: RetrievalResult | None
    sources: list[dict[str, Any]] = field(default_factory=list)
    template: str = ""
    latency_ms: dict[str, float] = field(default_factory=dict)

    @property
    def escalate(self) -> bool:
        return self.decision.escalate


class DarijaCareAssistant:
    """Wire the guard, the NLU service, the policy, the retriever and the responder."""

    def __init__(
        self,
        guard: InputGuard,
        nlu: NLUService,
        policy: DecisionPolicy,
        responder: Responder,
        retriever: Retriever | None = None,
    ) -> None:
        self.guard = guard
        self.nlu = nlu
        self.policy = policy
        self.responder = responder
        self.retriever = retriever

    def handle(self, text: str, state: ConversationState | None = None) -> AssistantReply:
        """Process one customer message."""
        timings: dict[str, float] = {}
        t0 = time.perf_counter()
        g = self.guard.check(text)
        nlu: NLUResult | None = None
        if g.allowed:
            t = time.perf_counter()
            nlu = self.nlu.predict(g.model_text)
            timings["nlu"] = (time.perf_counter() - t) * 1000
        decision = self.policy.decide(g, nlu, state)
        script = nlu.script if nlu else detect_script(g.masked_text)

        retrieval: RetrievalResult | None = None
        fiche_intent: str | None = None
        if decision.action is Action.RAG and nlu is not None:
            if self.retriever is not None:
                t = time.perf_counter()
                retrieval = self.retriever.search(g.masked_text, nlu.intent)
                timings["retrieval"] = (time.perf_counter() - t) * 1000
                if retrieval.reliable and retrieval.fiches:
                    fiche_intent = retrieval.fiches[0].intent
            else:  # no vector index available: use the predicted intent's fiche directly
                fiche_intent = nlu.intent

        rendered = self.responder.render(
            decision, script, nlu.intent if nlu else None, fiche_intent
        )
        timings["total"] = (time.perf_counter() - t0) * 1000
        return AssistantReply(
            rendered.text,
            g.masked_text,
            script,
            decision,
            nlu,
            retrieval,
            rendered.sources,
            rendered.template,
            timings,
        )


def build_assistant(
    root: Any = None,
    nlu_model: str = "v5",
    device: str | None = None,
    with_retriever: bool = True,
    qdrant_url: str | None = None,
) -> DarijaCareAssistant:
    """Assemble the real assistant from ``configs/`` (published NLU model, BGE-M3, Qdrant).

    Heavy imports happen here so that importing :mod:`darijacare.pipeline` stays light.
    ``qdrant_url`` selects the Qdrant server (the API passes its setting); otherwise
    ``QDRANT_URL`` or the local embedded store is used.
    """
    from darijacare.config import get_paths, load_yaml
    from darijacare.nlu.cli import load_train_config, model_spec
    from darijacare.nlu.service import LayaTelecomModel
    from darijacare.rag.cli import load_rag_config, make_embedder, make_retriever
    from darijacare.rag.kb import load_kb

    paths = get_paths(root)
    decision_cfg = load_yaml(paths.configs / "decision.yaml")
    rag_cfg = load_rag_config(paths)
    spec = model_spec(paths, load_train_config(paths), nlu_model)
    nlu = LayaTelecomModel(
        spec["abs_path"], device=device, model_version=f"{nlu_model}@{spec['revision'][:8]}"
    )
    fiches = load_kb(paths.root / rag_cfg["kb_dir"])
    retriever = (
        make_retriever(paths, rag_cfg, make_embedder(paths, rag_cfg, device), qdrant_url)
        if with_retriever
        else None
    )
    return DarijaCareAssistant(
        InputGuard.from_config(decision_cfg["input"]),
        nlu,
        DecisionPolicy(decision_cfg),
        Responder(fiches, max_chars=decision_cfg["input"]["max_chars"]),
        retriever,
    )
