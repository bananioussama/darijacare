"""Decision engine evaluated on a labelled split, from stored NLU predictions.

The policy (configs/decision.yaml) is replayed on every message with the NLU outputs
saved by the NLU evaluation (``reports/nlu/<model>/<split>/predictions.jsonl``), so no
model runs. Metrics (cahier des charges, Table 37):

* **critical errors**: messages that need a human (gold ``needs_human`` or urgency 3)
  but are not escalated;
* escalation rate and precision; clarification rate;
* accuracy of the automatic answers (rules 6 and 7: the fiche of the predicted intent
  is the gold intent's fiche);
* appropriate fallback: out-of-scope messages that get no telecom answer.

This is a measurement only: thresholds are never tuned on the official test set.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from darijacare.decision.policy import Action, DecisionPolicy
from darijacare.guards.input_guard import InputGuard
from darijacare.nlu.service import NLUResult, Scored

ANSWERS = {Action.RAG.value, Action.TEMPLATE.value}
ESCALATIONS = {Action.ESCALATE.value, Action.SAFETY_ESCALATE.value}


def nlu_from_prediction(text: str, row: Mapping[Any, Any]) -> NLUResult:
    """Rebuild the NLU result of one message from a stored prediction row."""
    return NLUResult(
        text=text,
        script=str(row["script_detected"]),
        category=str(row["category"]),
        category_confidence=float(row["category_p"]),
        intent=str(row["intent"]),
        intent_confidence=float(row["intent_p"]),
        intent_joint_confidence=float(row["intent_joint_p"]),
        product=str(row["product"]),
        product_confidence=float(row["product_p"]),
        urgency=int(row["urgency"]),
        urgency_confidence=float(row["urgency_p"]),
        needs_human=bool(row["needs_human"]),
        needs_human_probability=float(row["needs_human_p"]),
        category_top2=[Scored(str(label), float(p)) for label, p in row["category_top2"]],
        intent_top2=[Scored(str(label), float(p)) for label, p in row["intent_top2"]],
    )


def replay(gold: pd.DataFrame, predictions: pd.DataFrame, cfg: Mapping[str, Any]) -> pd.DataFrame:
    """One row per message: gold labels, predicted intent and the decision taken."""
    if len(gold) != len(predictions) or list(gold["id"]) != list(predictions["id"]):
        raise ValueError("Prédictions et données de référence non alignées")
    guard = InputGuard.from_config(cfg["input"])
    policy = DecisionPolicy(cfg)
    rows = []
    for g, p in zip(gold.to_dict("records"), predictions.to_dict("records"), strict=True):
        check = guard.check(str(g["text"]))
        nlu = nlu_from_prediction(check.model_text, p) if check.allowed else None
        decision = policy.decide(check, nlu)
        rows.append(
            {
                "id": g["id"],
                "script": g["script"],
                "intent": g["intent"],
                "category": g["category"],
                "needs_human": bool(g["needs_human"]),
                "urgency": int(g["urgency"]),
                "predicted_intent": p["intent"],
                "action": decision.action.value,
                "rule": decision.rule,
                "escalate": decision.escalate,
                "priority": decision.priority.score if decision.priority else None,
            }
        )
    return pd.DataFrame(rows)


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def summarize(df: pd.DataFrame, out_of_scope: Sequence[str] = ("non_telecom",)) -> dict[str, Any]:
    """Decision metrics of a replayed split (see the module docstring)."""
    must = df["needs_human"] | (df["urgency"] >= 3)
    critical = df[must & ~df["escalate"]]
    escalated = df[df["escalate"]]
    answered = df[df["action"].isin(ANSWERS)]
    oos = df[df["intent"].isin(out_of_scope)]
    oos_ok = oos["action"].isin({Action.OUT_OF_SCOPE.value, *ESCALATIONS, Action.CLARIFY.value})
    by_action = df["action"].value_counts().sort_index()
    return {
        "n": len(df),
        "actions": {str(k): int(v) for k, v in by_action.items()},
        "erreurs_critiques": {
            "a_escalader": int(must.sum()),
            "non_escalades": len(critical),
            "taux": _rate(len(critical), int(must.sum())),
            "par_ecriture": {
                str(s): int(n) for s, n in critical["script"].value_counts().sort_index().items()
            },
            "intentions": {
                str(i): int(n) for i, n in critical["intent"].value_counts().head(10).items()
            },
        },
        "escalade": {
            "taux": _rate(len(escalated), len(df)),
            "precision": _rate(
                int((escalated["needs_human"] | (escalated["urgency"] >= 3)).sum()), len(escalated)
            ),
        },
        "clarification": {
            "taux": _rate(int((df["action"] == Action.CLARIFY.value).sum()), len(df)),
        },
        "reponses_automatiques": {
            "taux": _rate(len(answered), len(df)),
            "exactitude": _rate(
                int((answered["predicted_intent"] == answered["intent"]).sum()), len(answered)
            ),
        },
        "hors_perimetre": {
            "messages": len(oos),
            "repli_approprie": _rate(int(oos_ok.sum()), len(oos)),
        },
    }


FROM_CITY_RE = re.compile(r"\bfrom ([^,]+)$")


def persona_parts(persona: str) -> tuple[str, str]:
    """(profession, city) of a persona such as ``"high-school teacher, Oujda"``."""
    if "," in persona:
        role, city = persona.rsplit(",", 1)
        return role.strip(), city.strip()
    m = FROM_CITY_RE.search(persona)  # e.g. "delivery driver from Tétouan"
    if m:
        return persona[: m.start()].strip(), m.group(1).strip()
    return persona.strip(), "inconnue"


def with_persona_parts(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``profession`` and ``ville`` columns derived from ``persona`` (fairness strata)."""
    if "persona" not in df:
        return df
    parts = [persona_parts(str(p)) for p in df["persona"]]
    return df.assign(profession=[r for r, _ in parts], ville=[c for _, c in parts])


def strata_accuracy(
    gold: pd.DataFrame, predictions: pd.DataFrame, columns: Sequence[str]
) -> dict[str, dict[str, dict[str, float | int]]]:
    """End-to-end intent accuracy by stratum (script, persona, generator…)."""
    correct = gold["intent"].to_numpy() == predictions["intent"].to_numpy()
    out: dict[str, dict[str, dict[str, float | int]]] = {}
    for column in columns:
        if column not in gold:
            continue
        frame = pd.DataFrame({"stratum": gold[column].astype(str), "ok": correct})
        grouped = frame.groupby("stratum")["ok"].agg(["mean", "size"]).sort_index()
        out[column] = {
            str(k): {"exactitude": round(float(r["mean"]), 4), "n": int(r["size"])}
            for k, r in grouped.iterrows()
        }
    return out
