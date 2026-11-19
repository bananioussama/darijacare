"""NLU latency benchmark (cahier des charges §8 and Tableau 37).

Targets: NLU p95 ≤ 300 ms per message on CPU, ≤ 50 ms on GPU (two passes, one message
at a time, as the API serves it). On CPU, int8 dynamic quantisation of the linear layers
(``torch.ao.quantization.quantize_dynamic``) is tried, and its outputs are compared
with the float model on the same messages: the prompt asks to check that the outputs
stay the same before adopting it.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from darijacare.nlu.service import NLUResult

LABELS: tuple[str, ...] = ("category", "intent", "product", "urgency", "needs_human")


def percentiles(ms: Sequence[float]) -> dict[str, float]:
    """p50, p95, p99, mean and max of latencies in milliseconds."""
    a = np.asarray(ms, dtype=float)
    return {
        "n": len(a),
        "p50": round(float(np.percentile(a, 50)), 1),
        "p95": round(float(np.percentile(a, 95)), 1),
        "p99": round(float(np.percentile(a, 99)), 1),
        "moyenne": round(float(a.mean()), 1),
        "max": round(float(a.max()), 1),
    }


def bench(
    predict: Callable[[str], NLUResult],
    texts: Sequence[str],
    warmup: int = 10,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[list[float], list[NLUResult]]:
    """Time ``predict`` on each text, one at a time, after ``warmup`` untimed calls."""
    for text in texts[:warmup]:
        predict(text)
    latencies, results = [], []
    for text in texts:
        start = clock()
        results.append(predict(text))
        latencies.append((clock() - start) * 1000)
    return latencies, results


def quantize_int8(service: Any) -> None:
    """Quantise the linear layers of the encoder of a :class:`LayaTelecomModel` to int8.

    Only the encoder (``agent.model.encoder``, mmBERT) is quantised: it holds nearly all
    the computation. The laya head is built from ``nn.TransformerEncoderLayer``, whose
    fast-path check reads ``linear.weight.device`` and fails on dynamically quantised
    linears (``weight`` becomes a method in torch 2.7), so it stays in float32.
    """
    import torch

    model = service.agent.model
    model.encoder = torch.ao.quantization.quantize_dynamic(  # type: ignore[no-untyped-call]
        model.encoder, {torch.nn.Linear}, dtype=torch.qint8
    )


def disable_autocast(service: Any) -> None:
    """Run a :class:`LayaTelecomModel` in float32 on GPU (diagnostic only).

    laya turns fp16 autocast on for CUDA GPUs of compute capability below 8
    (``Agent.amp_enabled``, set when the agent is loaded); Pascal GPUs compute slowly in
    fp16. Turning the flag off measures that cost; the served model keeps the default.
    """
    service.agent.amp_enabled = False


def agreement(reference: Sequence[NLUResult], other: Sequence[NLUResult]) -> dict[str, Any]:
    """Share of identical labels per task and largest probability differences."""
    if len(reference) != len(other):
        raise ValueError("Résultats de longueurs différentes")
    out: dict[str, Any] = {
        task: round(
            statistics.mean(
                getattr(a, task) == getattr(b, task) for a, b in zip(reference, other, strict=True)
            ),
            4,
        )
        for task in LABELS
    }
    out["identiques_sur_les_5_taches"] = round(
        statistics.mean(
            all(getattr(a, t) == getattr(b, t) for t in LABELS)
            for a, b in zip(reference, other, strict=True)
        ),
        4,
    )
    out["ecart_max_p_needs_human"] = round(
        max(
            abs(a.needs_human_probability - b.needs_human_probability)
            for a, b in zip(reference, other, strict=True)
        ),
        4,
    )
    out["ecart_max_confiance_intention"] = round(
        max(
            abs(a.intent_joint_confidence - b.intent_joint_confidence)
            for a, b in zip(reference, other, strict=True)
        ),
        4,
    )
    return out


def accuracy(results: Sequence[NLUResult], gold: Sequence[Mapping[Any, Any]]) -> dict[str, float]:
    """Accuracy of each task against gold labels (same order)."""
    return {
        task: round(
            statistics.mean(
                str(getattr(r, task)) == str(g[task]) for r, g in zip(results, gold, strict=True)
            ),
            4,
        )
        for task in LABELS
    }
