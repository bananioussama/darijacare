"""Phase 6 evaluations.

    python -m darijacare.quality.cli decision [--split test] [--nlu-model v5]
    python -m darijacare.quality.cli injections [--base-url https://127.0.0.1:8443/api]
    python -m darijacare.quality.cli robustness [--split test] [--nlu-model v5] [--device cuda]
    python -m darijacare.quality.cli latency [--device cpu] [--quantize]

Reports are written to ``reports/quality/``. The official test set is only measured,
never used to choose anything.
"""

from __future__ import annotations

import argparse
import json
import logging
from functools import partial
from pathlib import Path
from typing import Any

from darijacare.config import get_paths, load_yaml
from darijacare.io import read_jsonl, write_json, write_text

log = logging.getLogger("darijacare.quality")


def run_decision(split: str, nlu_model: str) -> dict[str, Any]:
    """Replay the decision policy on stored predictions; write the report."""
    from darijacare.quality.decision_eval import (
        replay,
        strata_accuracy,
        summarize,
        with_persona_parts,
    )

    paths = get_paths()
    gold = read_jsonl(paths.processed / f"{split}.jsonl")
    pred = read_jsonl(paths.reports / "nlu" / nlu_model / split / "predictions.jsonl")
    cfg = load_yaml(paths.configs / "decision.yaml")
    summary = summarize(replay(gold, pred, cfg))
    # Cahier des charges (biais et équité) : par écriture, par ville et par persona.
    summary["strates_intention"] = strata_accuracy(
        with_persona_parts(gold), pred, ["script", "ville", "profession", "generator", "round"]
    )
    summary.update({"split": split, "nlu_model": nlu_model})
    out = paths.reports / "quality"
    write_json(summary, out / f"decision_{split}.json")
    write_text(decision_markdown(summary), out / f"decision_{split}.md")
    return summary


def decision_markdown(s: dict[str, Any]) -> str:
    c, e, a = s["erreurs_critiques"], s["escalade"], s["reponses_automatiques"]
    lines = [
        f"# Moteur de décision rejoué sur `{s['split']}` (prédictions {s['nlu_model']})",
        "",
        f"{s['n']} messages. Mesure seule, aucun réglage (données synthétiques).",
        "",
        "| Mesure | Valeur |",
        "|---|---|",
        f"| Messages à escalader (needs_human ou urgence 3) | {c['a_escalader']} |",
        f"| **Erreurs critiques** (non escaladés) | **{c['non_escalades']}** ({c['taux']}) |",
        f"| Taux d'escalade / précision | {e['taux']} / {e['precision']} |",
        f"| Taux de clarification | {s['clarification']['taux']} |",
        f"| Réponses automatiques : taux / exactitude | {a['taux']} / {a['exactitude']} |",
        f"| Hors périmètre : repli approprié | {s['hors_perimetre']['repli_approprie']} |",
        "",
        "Actions : " + json.dumps(s["actions"], ensure_ascii=False),
        "",
        "Erreurs critiques par écriture : " + json.dumps(c["par_ecriture"], ensure_ascii=False),
        "",
        "Intentions des erreurs critiques : " + json.dumps(c["intentions"], ensure_ascii=False),
        "",
    ]
    for column, strata in s["strates_intention"].items():
        lines += [
            f"## Exactitude de l'intention par `{column}`",
            "",
            "| Strate | Exactitude | n |",
            "|---|---|---|",
        ]
        lines += [f"| {k} | {v['exactitude']:.3f} | {v['n']} |" for k, v in strata.items()]
        lines.append("")
    return "\n".join(lines)


def run_injections(
    base_url: str, verify: str | bool, pause: float, flood: int, baseline: Path | None
) -> dict[str, Any]:
    """Attack the running API (filter alone, then end to end); write the report."""
    import httpx
    from dotenv import dotenv_values

    from darijacare.guards.input_guard import InputGuard
    from darijacare.quality.injections import (
        Runner,
        false_positives,
        filter_detection,
        load_attacks,
        run_suite,
    )
    from darijacare.rag.kb import LANGS, SECTION_KEYS, load_kb

    paths = get_paths()
    attacks = load_attacks(paths.root / "tests" / "security" / "attacks.yaml")
    cfg = load_yaml(paths.configs / "decision.yaml")
    guard = InputGuard.from_config(cfg["input"])
    report: dict[str, Any] = {"cible": base_url, "filtre": filter_detection(guard, attacks)}
    if baseline is not None:
        old = InputGuard.from_config(load_yaml(baseline)["input"])
        report["filtre_reference"] = filter_detection(old, attacks)
    report["faux_positifs"] = {
        split: false_positives(guard, read_jsonl(paths.processed / f"{split}.jsonl")["text"])
        for split in ("train", "val", "test")
        if (paths.processed / f"{split}.jsonl").exists()
    }
    fiches = load_kb(paths.root / "kb")
    parts = [
        "\n".join([f.titles[lang], *(f.text(lang, k) for k in SECTION_KEYS)])
        for f in fiches.values()
        for lang in LANGS
    ]
    report["fiches"] = {"parties": len(parts), **false_positives(guard, parts)}

    env = dotenv_values(paths.root / ".env")
    secrets = [
        str(env.get(k) or "")
        for k in ("POSTGRES_PASSWORD", "JWT_SECRET", "DARIJACARE_ADMIN_PASSWORD")
    ]
    with httpx.Client(base_url=base_url, verify=verify, timeout=60) as client:
        runner = Runner(client, secrets=secrets, pause=pause)
        report["bout_en_bout"] = run_suite(runner, attacks, flood=flood)
    out = paths.reports / "quality"
    write_json(report, out / "injections.json")
    write_text(injections_markdown(report), out / "injections.md")
    return report


def injections_markdown(r: dict[str, Any]) -> str:
    """French summary of the adversarial evaluation."""
    f, e = r["filtre"], r["bout_en_bout"]
    a, iso = e["atypiques"], e["isolation"]
    lines = [
        "# Jeu de 50 attaques et entrées atypiques",
        "",
        f"Cible : `{r['cible']}` (pile Docker Compose, via le frontal nginx). "
        "Mesures sur données synthétiques.",
        "",
        "| Mesure | Valeur | Cible |",
        "|---|---|---|",
        f"| Attaques défendues (pas de 5xx, aucune fuite, sortie contrainte) | "
        f"**{e['defendues']}/{e['attaques']}** | 50/50 |",
        f"| Erreurs 5xx (attaques) | {e['erreurs_5xx']} | 0 |",
        f"| Détection par le filtre d'entrée | {f['detectees']}/{f['a_refuser']} ({f['taux']}) | "
        "première ligne seulement |",
    ]
    if "filtre_reference" in r:
        ref = r["filtre_reference"]
        lines.append(
            f"| Détection, filtre de la Phase 3 | {ref['detectees']}/{ref['a_refuser']} "
            f"({ref['taux']}) | — |"
        )
    fp = ", ".join(f"{k} {v['faux_positifs']}" for k, v in r["faux_positifs"].items())
    lines += [
        f"| Faux positifs du filtre (messages légitimes refusés) | {fp} | 0 |",
        f"| Fiches contenant un motif d'injection | {r['fiches']['faux_positifs']}/"
        f"{r['fiches']['parties']} parties | 0 |",
        f"| Entrées atypiques sans 5xx | {a['requetes'] - a['erreurs_5xx']}/{a['requetes']} | "
        "toutes |",
        f"| Lecture de l'historique par une autre session | {iso['lecture_par_autre_session']} "
        f"({'refusée' if iso['refusee'] else 'ACCEPTÉE'}) | refusée |",
        "| Historique de la victime intact après les attaques | "
        f"{'oui' if iso['historique_victime_intact'] else 'NON'} | oui |",
    ]
    if "abus_debit" in e:
        fl = e["abus_debit"]
        lines.append(
            f"| Rafale de {fl['requetes']} messages : statuts | "
            f"{json.dumps(fl['statuts'])} | 429, aucun 5xx |"
        )
    problems = json.dumps(e["problemes"], ensure_ascii=False) if e["problemes"] else "aucun"
    lines += [
        "",
        f"Attaques non détectées par le filtre : {', '.join(f['manquees']) or 'aucune'}.",
        "",
        "Détection par famille : " + json.dumps(f["par_famille"], ensure_ascii=False),
        "",
        "Défense par famille : " + json.dumps(e["par_famille"], ensure_ascii=False),
        "",
        "Défense par écriture : " + json.dumps(e["par_ecriture"], ensure_ascii=False),
        "",
        "Actions prises : " + json.dumps(e["actions"], ensure_ascii=False),
        "",
        f"Problèmes : {problems}",
        "",
        "## Entrées atypiques",
        "",
        "| Cas | Statut | Action |",
        "|---|---|---|",
    ]
    lines += [f"| {w['description']} | {w['statut']} | {w['action'] or '—'} |" for w in a["detail"]]
    lines.append("")
    return "\n".join(lines)


def _progress(kind: str, done: int, total: int) -> None:
    log.info("[%s] %d/%d", kind, done, total)


def run_robustness(
    split: str, nlu_model: str, device: str | None, kinds: list[str], seed: int
) -> dict[str, Any]:
    """Perturb a labelled split, predict through the production path, compare."""
    import pandas as pd

    from darijacare.guards.input_guard import InputGuard
    from darijacare.io import write_jsonl
    from darijacare.nlu.cli import _service, load_train_config
    from darijacare.nlu.evaluate import run_predictions
    from darijacare.quality.robustness import compare, perturb_texts, production_text

    paths = get_paths()
    gold = read_jsonl(paths.processed / f"{split}.jsonl")
    reference = read_jsonl(paths.reports / "nlu" / nlu_model / split / "predictions.jsonl")
    if list(reference["id"]) != list(gold["id"]):
        raise ValueError("Prédictions de référence non alignées sur le split")
    guard = InputGuard.from_config(load_yaml(paths.configs / "decision.yaml")["input"])
    cache = paths.reports / "quality" / "robustness" / nlu_model / split
    service = None
    perturbed: dict[str, tuple[list[str], pd.DataFrame]] = {}
    for kind in kinds:
        texts = perturb_texts(gold, kind, seed)
        path = cache / f"{kind}.jsonl"
        if path.exists():
            pred = read_jsonl(path)
            if list(pred["id"]) != list(gold["id"]):
                raise ValueError(f"{path} ne correspond pas au split")
        else:
            if service is None:
                service = _service(paths, load_train_config(paths), nlu_model, device)
            frame = gold.assign(text=[production_text(guard, t) for t in texts])
            pred = run_predictions(service, frame, progress=partial(_progress, kind))
            pred.insert(1, "text", texts)
            write_jsonl(pred, path)
        perturbed[kind] = (texts, pred)
    report = compare(gold, reference, perturbed)
    report.update({"split": split, "nlu_model": nlu_model, "seed": seed})
    out = paths.reports / "quality"
    write_json(report, out / f"robustness_{split}.json")
    write_text(robustness_markdown(report), out / f"robustness_{split}.md")
    return report


def robustness_markdown(r: dict[str, Any]) -> str:
    """French summary of the perturbation test."""
    from darijacare.quality.robustness import PERTURB

    ref = r["reference"]
    lines = [
        f"# Test de perturbation du NLU — `{r['split']}` (modèle {r['nlu_model']})",
        "",
        "Mesure finale sur le test officiel, aucun réglage (données synthétiques). Chemin de "
        "production : assainissement et masquage de l'entrée, puis modèle servi. Graine "
        f"{r['seed']}. Cible : baisse du F1 macro d'intention ≤ 5 points.",
        "",
        "| Perturbation | Messages modifiés | F1 macro intention | Baisse (points) | "
        "Exactitude bout en bout | Cible |",
        "|---|---|---|---|---|---|",
        f"| aucune (référence) | — | {ref['intent_f1_macro']:.4f} | — | "
        f"{ref['intent_end_to_end']:.4f} | — |",
    ]
    for kind, m in r["perturbations"].items():
        lines.append(
            f"| {kind} | {m['messages_modifies']:.1%} | {m['intent_f1_macro']:.4f} | "
            f"{m['baisse_f1_points']:.2f} | {m['intent_end_to_end']:.4f} | "
            f"{'atteinte' if m['cible_atteinte'] else 'NON atteinte'} |"
        )
    lines += ["", "## Baisse par écriture (points de F1 macro d'intention)", ""]
    scripts = sorted({s for m in r["perturbations"].values() for s in m["par_ecriture"]})
    lines += ["| Perturbation | " + " | ".join(scripts) + " |", "|---|" + "---|" * len(scripts)]
    for kind, m in r["perturbations"].items():
        cells = [f"{m['par_ecriture'][s]['baisse_points']:.2f}" for s in scripts]
        lines.append(f"| {kind} | " + " | ".join(cells) + " |")
    lines += ["", "## Exemples (phrases d'exemple de l'interface, pas le test)", ""]
    import random

    sample = "chargit 20dh w ma wslatni walo, 3afak chofo lia"
    sample_ar = "كيفاش نشري باس ديال الأنترنيت"
    for kind, fn in PERTURB.items():
        a = fn(sample, random.Random(f"{r['seed']}:{kind}:exemple"))
        b = fn(sample_ar, random.Random(f"{r['seed']}:{kind}:exemple-ar"))
        lines.append(f"- **{kind}** : `{a}` · `{b}`")
    lines.append("")
    return "\n".join(lines)


def run_latency(
    device: str,
    n: int,
    warmup: int,
    quantize: bool,
    threads: int | None,
    nlu_model: str,
    no_amp: bool = False,
) -> dict[str, Any]:
    """Benchmark the NLU one message at a time (validation sample); write the report."""
    import platform

    import torch

    from darijacare.guards.input_guard import InputGuard
    from darijacare.nlu.cli import _service, load_train_config
    from darijacare.quality.latency import (
        accuracy,
        agreement,
        bench,
        disable_autocast,
        percentiles,
        quantize_int8,
    )
    from darijacare.quality.robustness import production_text

    paths = get_paths()
    cfg = load_train_config(paths)
    if threads:
        torch.set_num_threads(threads)
    guard = InputGuard.from_config(load_yaml(paths.configs / "decision.yaml")["input"])
    sample = read_jsonl(paths.processed / "val.jsonl").sample(n, random_state=int(cfg["seed"]))
    texts = [production_text(guard, t) for t in sample["text"]]
    gold = sample.to_dict("records")
    service = _service(paths, cfg, nlu_model, device)
    latencies, results = bench(service.predict, texts, warmup)
    report: dict[str, Any] = {
        "appareil": device,
        "materiel": (
            torch.cuda.get_device_name(0) if device.startswith("cuda") else platform.processor()
        ),
        "threads_torch": torch.get_num_threads(),
        "torch": torch.__version__,
        "modele": nlu_model,
        "messages": n,
        "echauffement": warmup,
        "float": {**percentiles(latencies), "exactitude": accuracy(results, gold)},
    }
    if quantize:
        if device != "cpu":
            raise SystemExit("La quantification dynamique int8 ne s'applique que sur CPU.")
        quantize_int8(service)
        lat_q, res_q = bench(service.predict, texts, warmup)
        report["int8"] = {
            **percentiles(lat_q),
            "exactitude": accuracy(res_q, gold),
            "accord_avec_float": agreement(results, res_q),
        }
    if no_amp:
        if not device.startswith("cuda"):
            raise SystemExit("--no-amp ne concerne que le GPU (autocast fp16 de laya).")
        disable_autocast(service)
        lat_f, res_f = bench(service.predict, texts, warmup)
        report["fp32"] = {
            **percentiles(lat_f),
            "exactitude": accuracy(res_f, gold),
            "accord_avec_float": agreement(results, res_f),
        }
    out = paths.reports / "quality"
    write_json(report, out / f"latency_{device.split(':')[0]}.json")
    reports = [
        json.loads(f.read_text(encoding="utf-8")) for f in sorted(out.glob("latency_*.json"))
    ]
    write_text(latency_markdown(reports), out / "latency.md")
    return report


VARIANT_LABELS = {
    ("cpu", "float"): "float32 (servi)",
    ("cpu", "int8"): "int8 dynamique",
    ("cuda", "float"): "autocast fp16 (défaut de laya)",
    ("cuda", "fp32"): "float32 (diagnostic)",
}


def latency_markdown(reports: list[dict[str, Any]]) -> str:
    """French summary of every latency run found in ``reports/quality``."""
    lines = [
        "# Latence du NLU (deux passes, un message à la fois)",
        "",
        "Échantillon de la validation passé par le chemin de production (assainissement, "
        "masquage). Cibles : p95 ≤ 300 ms sur CPU, ≤ 50 ms sur GPU.",
        "",
        "| Appareil | Variante | Threads | p50 (ms) | p95 (ms) | p99 (ms) | Exactitude intention | "
        "Cible p95 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        target = 300 if r["appareil"] == "cpu" else 50
        for variant in ("float", "int8", "fp32"):
            if variant not in r:
                continue
            m = r[variant]
            ok = "atteinte" if m["p95"] <= target else "NON atteinte"
            label = VARIANT_LABELS[(r["appareil"].split(":")[0], variant)]
            lines.append(
                f"| {r['appareil']} ({r['materiel']}) | {label} | {r['threads_torch']} | "
                f"{m['p50']} | {m['p95']} | {m['p99']} | {m['exactitude']['intent']} | "
                f"{ok} ({target} ms) |"
            )
    for r in reports:
        for variant in ("int8", "fp32"):
            if variant in r:
                a = r[variant]["accord_avec_float"]
                lines += [
                    "",
                    f"Accord {variant} / défaut ({r['appareil']}) sur {r['messages']} messages : "
                    + json.dumps(a, ensure_ascii=False),
                ]
    lines.append("")
    return "\n".join(lines)


def load_stats(prefix: Path) -> dict[str, Any]:
    """Main figures of a Locust run (``<prefix>_stats.csv`` and ``_failures.csv``)."""
    import csv

    with (prefix.parent / f"{prefix.name}_stats.csv").open(encoding="utf-8") as f:
        rows = {r["Name"]: r for r in csv.DictReader(f)}
    out: dict[str, Any] = {}
    for name, r in rows.items():
        out[name] = {
            "requetes": int(r["Request Count"]),
            "echecs": int(r["Failure Count"]),
            "par_seconde": round(float(r["Requests/s"]), 2),
            "p50_ms": float(r["50%"]),
            "p95_ms": float(r["95%"]),
            "p99_ms": float(r["99%"]),
            "max_ms": round(float(r["Max Response Time"]), 1),
        }
    failures = prefix.parent / f"{prefix.name}_failures.csv"
    if failures.exists():
        with failures.open(encoding="utf-8") as f:
            # One entry per endpoint and error (the same error can hit several endpoints).
            out["erreurs"] = {
                f"{r['Name']} : {r['Error']}": int(r["Occurrences"]) for r in csv.DictReader(f)
            }
    return out


def run_load_report(runs: list[tuple[str, Path]]) -> dict[str, Any]:
    """Summarise several Locust runs into ``reports/quality/load.{json,md}``."""
    report = {label: load_stats(prefix) for label, prefix in runs}
    out = get_paths().reports / "quality"
    write_json(report, out / "load.json")
    lines = [
        "# Tests de charge (Locust, via le frontal HTTPS)",
        "",
        "| Scénario | Point d'accès | Requêtes | Échecs | Req/s | p50 (ms) | p95 (ms) | p99 (ms) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for label, stats in report.items():
        for name, m in stats.items():
            if name == "erreurs":
                continue
            lines.append(
                f"| {label} | {name} | {m['requetes']} | {m['echecs']} | {m['par_seconde']} | "
                f"{m['p50_ms']:.0f} | {m['p95_ms']:.0f} | {m['p99_ms']:.0f} |"
            )
    for label, stats in report.items():
        if stats.get("erreurs"):
            lines += [
                "",
                f"Erreurs ({label}) : " + json.dumps(stats["erreurs"], ensure_ascii=False),
            ]
    lines.append("")
    write_text("\n".join(lines), out / "load.md")
    return report


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested evaluation."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="python -m darijacare.quality.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    de = sub.add_parser("decision", help="politique de décision rejouée sur un jeu étiqueté")
    de.add_argument("--split", default="test", choices=["val", "test"])
    de.add_argument("--nlu-model", default="v5")
    inj = sub.add_parser("injections", help="50 attaques et entrées atypiques sur l'API")
    inj.add_argument("--base-url", default="https://127.0.0.1:8443/api")
    inj.add_argument(
        "--ca", default=None, help="certificat à vérifier (défaut : deploy/certs/cert.pem)"
    )
    inj.add_argument("--pause", type=float, default=2.1, help="secondes entre deux messages")
    inj.add_argument("--flood", type=int, default=40, help="rafale finale (0 : aucune)")
    inj.add_argument("--baseline-config", type=Path, default=None)
    rob = sub.add_parser("robustness", help="test de perturbation du NLU (fautes, etc.)")
    rob.add_argument("--split", default="test", choices=["val", "test"])
    rob.add_argument("--nlu-model", default="v5")
    rob.add_argument("--device", default=None)
    rob.add_argument("--kinds", nargs="+", default=None)
    rob.add_argument("--seed", type=int, default=None)
    lat = sub.add_parser("latency", help="banc de latence du NLU (CPU ou GPU)")
    lat.add_argument("--device", default="cpu")
    lat.add_argument("--n", type=int, default=200)
    lat.add_argument("--warmup", type=int, default=10)
    lat.add_argument("--quantize", action="store_true", help="essai int8 dynamique (CPU)")
    lat.add_argument("--threads", type=int, default=None)
    lat.add_argument("--nlu-model", default="v5")
    lat.add_argument("--no-amp", action="store_true", help="diagnostic GPU : laya en float32")
    lr = sub.add_parser("load-report", help="résumé des CSV Locust (étiquette=préfixe)")
    lr.add_argument("runs", nargs="+", help="ex. capacite=reports/quality/load/capacite")
    args = parser.parse_args(argv)
    if args.cmd == "load-report":
        runs = [(r.split("=", 1)[0], Path(r.split("=", 1)[1])) for r in args.runs]
        run_load_report(runs)
    if args.cmd == "latency":
        r = run_latency(
            args.device,
            args.n,
            args.warmup,
            args.quantize,
            args.threads,
            args.nlu_model,
            args.no_amp,
        )
        log.info("p95 float %s ms", r["float"]["p95"])
    if args.cmd == "robustness":
        from darijacare.quality.robustness import KINDS

        seed = (
            args.seed
            if args.seed is not None
            else int(load_yaml(get_paths().configs / "train.yaml")["seed"])
        )
        r = run_robustness(args.split, args.nlu_model, args.device, args.kinds or list(KINDS), seed)
        for kind, m in r["perturbations"].items():
            log.info("%s : baisse %.2f points", kind, m["baisse_f1_points"])
    if args.cmd == "decision":
        s = run_decision(args.split, args.nlu_model)
        log.info("erreurs critiques : %s", s["erreurs_critiques"])
    elif args.cmd == "injections":
        cert = Path(args.ca) if args.ca else get_paths().root / "deploy" / "certs" / "cert.pem"
        verify: str | bool = str(cert) if cert.exists() else True
        r = run_injections(args.base_url, verify, args.pause, args.flood, args.baseline_config)
        e = r["bout_en_bout"]
        log.info(
            "défendues %s/%s, filtre %s/%s",
            e["defendues"],
            e["attaques"],
            r["filtre"]["detectees"],
            r["filtre"]["a_refuser"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
