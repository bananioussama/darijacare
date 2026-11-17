"""Retrain the Laya telecom classifier on *our* split, with the published recipe.

Recipe (model card of ``mballouch/jev-darija-telecom-model``, v5):

* start from ``mballouch/jev-darija`` (Laya multilingual already tuned on Darija);
* train all 22 encoder blocks and the decision layers (head, scorer, act head,
  type embeddings): ~125 M parameters; **token embeddings frozen**;
* soft cross-entropy with label smoothing 0.05; option order shuffled for
  ``choice`` questions;
* AdamW, learning rate 3e-5 (encoder) / 1e-4 (head), 6 % linear warm-up then
  cosine decay, effective batch 32, fp16 on GPU;
* keep the best epoch on validation, then fit confidence temperatures on it.

Building blocks come from ``laya.train`` (item encoding, option shuffling, loss,
checkpoint I/O, temperature fitting) so the training items are exactly what
inference sees. What this module adds: the warm-up schedule (``laya.train`` only
has cosine), freezing the token embeddings only (``laya`` can only freeze the
whole encoder), per-epoch validation with best-epoch selection, several seeds
and resumable runs (a Kaggle session is limited to 12 h).

Questions per training row: category, product, urgency, needs_human, and the
intent question of the row's *own* category (taxonomy note: "Training asks the
category question plus the row's own category intent question").
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from darijacare.config import Paths, get_paths, load_yaml
from darijacare.io import read_jsonl, write_json
from darijacare.nlu.service import build_questions

log = logging.getLogger("darijacare.nlu.train")

FROZEN_PREFIXES = ("encoder.embeddings.tok_embeddings.",)


@dataclass
class RetrainConfig:
    """Hyperparameters (``configs/train.yaml`` -> ``retrain``)."""

    start_checkpoint: str = "models/jev-darija"
    epochs: int = 9
    micro_batch: int = 8
    grad_accum: int = 4
    encoder_lr: float = 3e-5
    head_lr: float = 1e-4
    min_lr: float = 0.0
    warmup_frac: float = 0.06
    weight_decay: float = 0.01
    grad_clip: float = 1.0
    label_smoothing: float = 0.05
    shuffle_options: tuple[str, ...] = ("choice",)
    amp: bool = True
    gradient_checkpointing: bool = True
    seeds: tuple[int, ...] = (42, 43, 44)
    val_batch_size: int = 32
    max_train_rows: int | None = None
    max_val_rows: int | None = None
    frozen_prefixes: tuple[str, ...] = field(default=FROZEN_PREFIXES)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> RetrainConfig:
        known = {f for f in cls.__dataclass_fields__}
        kw = {k: (tuple(v) if isinstance(v, list) else v) for k, v in data.items() if k in known}
        return cls(**kw)  # type: ignore[arg-type]


# --- data --------------------------------------------------------------------


def build_rows(df: Any, taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    """``{state, questions, expected}`` rows for ``laya.train.items_from_rows``."""
    first, intent_q = build_questions(taxonomy)
    rows = []
    for r in df.itertuples(index=False):
        questions = dict(first)
        expected: dict[str, Any] = {
            "category": r.category,
            "product": r.product,
            "urgency": int(r.urgency),
            "needs_human": bool(r.needs_human),
        }
        if r.category in intent_q:
            questions["intent"] = intent_q[r.category]
            expected["intent"] = r.intent
        rows.append({"state": r.text, "questions": questions, "expected": expected})
    return rows


def lr_lambda(step: int, total: int, warmup: int, min_ratio: float) -> float:
    """Linear warm-up to 1, then cosine decay to ``min_ratio``."""
    if warmup > 0 and step < warmup:
        return (step + 1) / warmup
    progress = (step - warmup) / max(1, total - warmup)
    return min_ratio + (1 - min_ratio) * 0.5 * (1 + math.cos(math.pi * min(1.0, progress)))


def trainable_report(model: Any) -> dict[str, int]:
    """Count trainable and frozen parameters."""
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    frozen = sum(p.numel() for p in model.parameters() if not p.requires_grad)
    return {"trainable": int(trainable), "frozen": int(frozen)}


# --- one seed ----------------------------------------------------------------


def train_one_seed(
    paths: Paths, cfg: RetrainConfig, seed: int, out_root: Path, device_name: str | None = None
) -> dict[str, Any]:
    """Train one seed; keeps ``best/`` (loadable by ``laya.load``) and ``state.pt`` to resume."""
    import torch
    from laya.calibrate import fit_temperature_map
    from laya.common import collate_items, uses_parallel_layout
    from laya.train import (
        _forward,
        calibration_records,
        draw_option_order,
        encode_item,
        items_from_rows,
        load_checkpoint,
        resolve_device,
        save_checkpoint,
        soft_ce_loss,
    )

    from darijacare.nlu.metrics import intent_end_to_end
    from darijacare.nlu.service import LayaTelecomModel

    out = out_root / f"seed{seed}"
    out.mkdir(parents=True, exist_ok=True)
    device = resolve_device(device_name or "auto")
    amp = cfg.amp and device.type == "cuda"
    random.seed(seed)
    torch.manual_seed(seed)

    taxonomy = json.loads((paths.raw / "telecom_taxonomy.json").read_text(encoding="utf-8"))
    train_df = read_jsonl(paths.processed / "train.jsonl")
    val_df = read_jsonl(paths.processed / "val.jsonl")
    if cfg.max_train_rows:
        train_df = train_df.sample(cfg.max_train_rows, random_state=seed).reset_index(drop=True)
    if cfg.max_val_rows:
        val_df = val_df.sample(cfg.max_val_rows, random_state=seed).reset_index(drop=True)

    model, tok, ckpt_cfg = load_checkpoint(str(paths.root / cfg.start_checkpoint))
    max_len = int(ckpt_cfg.get("max_len", 512))
    head_max_len = int(ckpt_cfg.get("head_max_len", 192))
    parallel = uses_parallel_layout(ckpt_cfg)
    items, skipped = items_from_rows(
        tok, build_rows(train_df, taxonomy), max_len, head_max_len, cfg.label_smoothing
    )
    val_items, _ = items_from_rows(tok, build_rows(val_df, taxonomy), max_len, head_max_len, 0.0)
    if skipped:
        log.warning("Items ignorés : %s", skipped)

    for name, p in model.named_parameters():
        p.requires_grad_(not name.startswith(cfg.frozen_prefixes))
    counts = trainable_report(model)
    log.info(
        "Paramètres entraînés %s, gelés %s", f"{counts['trainable']:,}", f"{counts['frozen']:,}"
    )
    if (
        cfg.gradient_checkpointing
        and amp
        and hasattr(model.encoder, "gradient_checkpointing_enable")
    ):
        model.encoder.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={"use_reentrant": False}
        )
        model.head_checkpointing = True
    model.to(device)

    groups = [
        {
            "params": [
                p
                for n, p in model.named_parameters()
                if n.startswith("encoder.") and p.requires_grad
            ],
            "lr": cfg.encoder_lr,
        },
        {
            "params": [
                p
                for n, p in model.named_parameters()
                if not n.startswith("encoder.") and p.requires_grad
            ],
            "lr": cfg.head_lr,
        },
    ]
    optimizer = torch.optim.AdamW(groups, weight_decay=cfg.weight_decay)
    steps_per_epoch = math.ceil(len(items) / cfg.micro_batch)
    updates_per_epoch = math.ceil(steps_per_epoch / cfg.grad_accum)
    total_updates = updates_per_epoch * cfg.epochs
    warmup = int(cfg.warmup_frac * total_updates)
    min_ratio = cfg.min_lr / cfg.encoder_lr if cfg.encoder_lr else 0.0
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda s: lr_lambda(s, total_updates, warmup, min_ratio)
    )
    scaler = torch.amp.GradScaler("cuda") if amp else None  # type: ignore[attr-defined]
    params = [p for g in groups for p in g["params"]]  # type: ignore[attr-defined]

    history: list[dict[str, Any]] = []
    best = {"epoch": -1, "val_intent_end_to_end": -1.0}
    start_epoch = 0
    state_path = out / "state.pt"
    if state_path.exists():
        state = torch.load(state_path, map_location="cpu", weights_only=False)
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])  # type: ignore[no-untyped-call]
        if scaler is not None and state.get("scaler"):
            scaler.load_state_dict(state["scaler"])
        history, best, start_epoch = state["history"], state["best"], state["epoch"] + 1
        log.info("Reprise à l'époque %d", start_epoch + 1)

    for epoch in range(start_epoch, cfg.epochs):
        model.train()
        t0 = time.time()
        epoch_items = list(items)
        random.Random(seed + epoch).shuffle(epoch_items)
        # Advance the option-order RNG deterministically per epoch so resumed runs match.
        order_rng = random.Random(seed * 1000 + epoch)
        total, n_steps = 0.0, 0
        optimizer.zero_grad(set_to_none=True)
        for start in range(0, len(epoch_items), cfg.micro_batch):
            chunk = [
                encode_item(
                    tok,
                    it,
                    max_len,
                    head_max_len,
                    draw_option_order(it, order_rng, cfg.shuffle_options),
                    parallel,
                )
                for it in epoch_items[start : start + cfg.micro_batch]
            ]
            batch = collate_items([chunk], tok.pad_token_id)
            logits = _forward(model, batch, device, amp, False)
            loss = soft_ce_loss(logits, batch["target"].to(device), batch["marker_mask"].to(device))
            window_start = (n_steps // cfg.grad_accum) * cfg.grad_accum
            window = min(cfg.grad_accum, steps_per_epoch - window_start)
            if scaler is not None:
                scaler.scale(loss / window).backward()
            else:
                (loss / window).backward()
            n_steps += 1
            if n_steps % cfg.grad_accum == 0 or start + cfg.micro_batch >= len(epoch_items):
                if scaler is not None:
                    scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(params, cfg.grad_clip)
                if scaler is not None:
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
            total += float(loss.item())
            if n_steps == 200:
                per_step = (time.time() - t0) / n_steps
                eta_epoch = per_step * steps_per_epoch / 3600
                log.info(
                    "Estimation : %.2f s/pas, ~%.1f h par époque, ~%.1f h pour %d époques",
                    per_step,
                    eta_epoch,
                    eta_epoch * (cfg.epochs - epoch),
                    cfg.epochs - epoch,
                )
            if n_steps % 500 == 0:
                log.info(
                    "époque %d pas %d/%d perte %.4f",
                    epoch + 1,
                    n_steps,
                    steps_per_epoch,
                    total / n_steps,
                )

        # Validation: save this epoch as a laya checkpoint and run the two-pass inference.
        model.eval()
        ep_dir = out / "last_epoch"
        save_checkpoint(
            model, tok, dict(ckpt_cfg, max_len=max_len, head_max_len=head_max_len), str(ep_dir)
        )
        shutil.copyfile(paths.raw / "telecom_taxonomy.json", ep_dir / "telecom_taxonomy.json")
        service = LayaTelecomModel(ep_dir, device=str(device))
        preds = service.predict_batch(val_df["text"].tolist(), batch_size=cfg.val_batch_size)
        import pandas as pd

        pred_df = pd.DataFrame(
            {"category": [p.category for p in preds], "intent": [p.intent for p in preds]}
        )
        score = intent_end_to_end(val_df[["category", "intent"]], pred_df)
        del service
        record = {
            "epoch": epoch + 1,
            "train_loss": total / max(1, n_steps),
            "val_intent_end_to_end": score,
            "minutes": (time.time() - t0) / 60,
        }
        history.append(record)
        log.info("Époque %d : %s", epoch + 1, record)
        if score > best["val_intent_end_to_end"]:
            best = {"epoch": epoch + 1, "val_intent_end_to_end": score}
            if (out / "best").exists():
                shutil.rmtree(out / "best")
            shutil.copytree(ep_dir, out / "best")
        torch.save(
            {
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "scheduler": scheduler.state_dict(),  # type: ignore[no-untyped-call]
                "scaler": scaler.state_dict() if scaler is not None else None,
                "history": history,
                "best": best,
                "epoch": epoch,
            },
            state_path,
        )

    # Confidence temperatures fitted on the validation items, on the best epoch (as laya does).
    best_model, best_tok, best_cfg = load_checkpoint(str(out / "best"))
    best_model.to(device)
    records = calibration_records(
        best_model, best_tok, val_items, device, max_len, head_max_len, parallel=parallel
    )
    fitted = fit_temperature_map(records)
    best_cfg = dict(best_cfg, fine_tuned=True, temperature=fitted["temperature"])
    best_cfg.pop("temperature_by_options", None)
    if fitted["temperature_by_options"]:
        best_cfg["temperature_by_options"] = fitted["temperature_by_options"]
    best_cfg["training"] = {
        "task": "darija_telecom",
        "selected_epoch": best["epoch"],
        "darijacare_retrain": asdict(cfg),
        "seed": seed,
    }
    save_checkpoint(best_model, best_tok, best_cfg, str(out / "best"))
    shutil.copyfile(paths.raw / "telecom_taxonomy.json", out / "best" / "telecom_taxonomy.json")
    summary = {
        "seed": seed,
        "best": best,
        "history": history,
        "params": counts,
        "temperature": fitted["temperature"],
        "train_items": len(items),
    }
    write_json(summary, out / "summary.json")
    return summary


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m darijacare.nlu.train [--seeds 42 43 44] [--out models/retrain]``."""
    parser = argparse.ArgumentParser(prog="darijacare-train")
    parser.add_argument("--seeds", type=int, nargs="*", default=None)
    parser.add_argument("--out", default="models/retrain")
    parser.add_argument("--device", default=None)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Essai rapide : 1 époque, 64 lignes de train, 32 de validation",
    )
    parser.add_argument(
        "--micro-batch",
        type=int,
        default=None,
        help="Taille de micro-batch (le batch effectif reste micro x accumulation)",
    )
    parser.add_argument("--grad-accum", type=int, default=None)
    parser.add_argument("--epochs", type=int, default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")

    paths = get_paths()
    tcfg = load_yaml(paths.configs / "train.yaml")
    cfg = RetrainConfig.from_mapping(tcfg["retrain"])
    if args.smoke:
        cfg.epochs, cfg.max_train_rows, cfg.max_val_rows, cfg.seeds = 1, 64, 32, (cfg.seeds[0],)
    for name in ("micro_batch", "grad_accum", "epochs"):
        if getattr(args, name) is not None:
            setattr(cfg, name, getattr(args, name))
    seeds = tuple(args.seeds) if args.seeds else cfg.seeds
    out_root = paths.root / args.out
    summaries = [train_one_seed(paths, cfg, s, out_root, args.device) for s in seeds]
    scores = [s["best"]["val_intent_end_to_end"] for s in summaries]
    mean = sum(scores) / len(scores)
    sd = (sum((x - mean) ** 2 for x in scores) / max(1, len(scores) - 1)) ** 0.5
    write_json(
        {"seeds": list(seeds), "val_intent_end_to_end": scores, "mean": mean, "sd": sd},
        out_root / "summary.json",
    )
    log.info("Validation (intention bout en bout) : moyenne %.4f, écart-type %.4f", mean, sd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
