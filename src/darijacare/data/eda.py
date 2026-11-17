"""Automatic exploratory data analysis report (cahier des charges, F-DAT-02).

Produces ``reports/eda/README.md`` (French) and PNG figures:

* distributions by script, category, intent, product, urgency, needs_human,
  generator and round, for the raw official splits and the final splits;
* message lengths; class imbalance; intent x category co-occurrence;
* a cross-check against Table 5 of the specification (reference values in
  ``configs/data.yaml``), flagged when the gap exceeds ``tolerance_points``.

Figures are written with fixed settings and no timestamp metadata so that
re-running the stage gives byte-identical files with the same library versions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure

from darijacare.config import Paths
from darijacare.data.scripts import detect_script
from darijacare.data.taxonomy import load_taxonomy
from darijacare.io import read_jsonl, write_json, write_text

log = logging.getLogger(__name__)

# Palette DarijaCare (cahier des charges, charte graphique).
VIOLET = "#7B2CBF"
NIGHT = "#24093F"
LAVENDER = "#E9DDF9"
INK = "#1E1530"
MUTED = "#6B6280"
GRID = "#E4DFEC"
SEQ_CMAP = LinearSegmentedColormap.from_list("darijacare_seq", ["#F4F1F8", LAVENDER, VIOLET, NIGHT])

PNG_META = {"Software": None}


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK,
            "axes.titlecolor": INK,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "figure.dpi": 100,
            "savefig.dpi": 110,
            "svg.hashsalt": "darijacare",
        }
    )


def pct(series: pd.Series) -> dict[str, float]:
    """Percentage of each value, rounded to 0.1, keyed by ``str(value)`` and sorted."""
    vc = series.astype(str).value_counts(normalize=True).sort_index() * 100
    return {str(k): round(float(v), 1) for k, v in vc.items()}


def summarize(df: pd.DataFrame) -> dict[str, Any]:
    """Headline statistics for one split (Table 5 layout)."""
    lengths = df["text"].str.len()
    per_intent = df["intent"].value_counts()
    return {
        "rows": len(df),
        "script_pct": pct(df["script"]),
        "needs_human_pct": round(float(df["needs_human"].mean() * 100), 1),
        "urgency_pct": pct(df["urgency"]),
        "product_unknown_pct": round(float((df["product"] == "unknown").mean() * 100), 1),
        "non_telecom_pct": round(float((df["intent"] == "non_telecom").mean() * 100), 1),
        "length_mean": round(float(lengths.mean()), 1),
        "length_median": float(lengths.median()),
        "length_max": int(lengths.max()),
        "length_min": int(lengths.min()),
        "intents": int(df["intent"].nunique()),
        "categories": int(df["category"].nunique()),
        "per_intent_min": int(per_intent.min()),
        "per_intent_max": int(per_intent.max()),
        "imbalance_ratio_intent": round(float(per_intent.max() / per_intent.min()), 2),
        "generator_pct": pct(df["generator"]),
        "round_pct": pct(df["round"]),
    }


def compare_reference(
    stats: dict[str, Any], ref: dict[str, Any], tol: float
) -> list[dict[str, Any]]:
    """Compare measured statistics with Table 5 values; flag gaps above ``tol``."""
    rows: list[dict[str, Any]] = []

    def add(name: str, measured: float, expected: float, tolerance: float = tol) -> None:
        gap = round(abs(float(measured) - float(expected)), 2)
        rows.append(
            {
                "indicateur": name,
                "mesuré": measured,
                "référence": expected,
                "écart": gap,
                "ok": gap <= tolerance,
            }
        )

    add("lignes", stats["rows"], ref["rows"], 0)
    for k, v in ref["script_pct"].items():
        add(f"script {k} (%)", stats["script_pct"].get(str(k), 0.0), v)
    add("needs_human (%)", stats["needs_human_pct"], ref["needs_human_pct"])
    for k, v in ref["urgency_pct"].items():
        add(f"urgence {k} (%)", stats["urgency_pct"].get(str(k), 0.0), v)
    add("produit unknown (%)", stats["product_unknown_pct"], ref["product_unknown_pct"])
    add("longueur moyenne", stats["length_mean"], ref["length_mean"], 0.1)
    add("longueur médiane", stats["length_median"], ref["length_median"], 0.5)
    add("longueur max", stats["length_max"], ref["length_max"], 0)
    return rows


# --- Figures ----------------------------------------------------------------


def _save(fig: Figure, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="png", metadata=PNG_META, bbox_inches="tight")
    plt.close(fig)
    return path.name


def bar_figure(counts: pd.Series, title: str, path: Path, horizontal: bool = False) -> str:
    """Single-series bar chart (one hue, thin bars, value labels on the ends only)."""
    n = len(counts)
    if horizontal:
        fig, ax = plt.subplots(figsize=(7.5, max(2.2, 0.17 * n + 0.8)))
        ax.barh(range(n), counts.to_numpy(), color=VIOLET, height=0.7)
        ax.set_yticks(range(n), counts.index.astype(str), fontsize=7 if n > 20 else 9)
        ax.invert_yaxis()
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("messages")
    else:
        fig, ax = plt.subplots(figsize=(max(4.0, 0.6 * n + 1.5), 3.2))
        ax.bar(range(n), counts.to_numpy(), color=VIOLET, width=0.6)
        ax.set_xticks(
            range(n),
            counts.index.astype(str),
            rotation=30 if n > 4 else 0,
            ha="right" if n > 4 else "center",
        )
        ax.grid(axis="x", visible=False)
        ax.set_ylabel("messages")
        total = counts.sum()
        for i, v in enumerate(counts.to_numpy()):
            ax.text(i, v, f"{v / total:.1%}", ha="center", va="bottom", color=INK, fontsize=8)
    ax.set_title(title, loc="left")
    return _save(fig, path)


def length_figure(df: pd.DataFrame, path: Path) -> str:
    """Histogram of message length (characters), one panel per script."""
    scripts = ["arabic", "arabizi", "mixed"]
    fig, axes = plt.subplots(1, 3, figsize=(10, 2.8), sharey=True)
    bins = np.arange(0, 260, 10)
    for ax, s in zip(axes, scripts, strict=True):
        ax.hist(
            df.loc[df["script"] == s, "text"].str.len(),
            bins=bins,
            color=VIOLET,
            edgecolor="white",
            linewidth=0.8,
        )
        ax.set_title(s, loc="left")
        ax.set_xlabel("caractères")
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("messages")
    fig.suptitle(
        "Longueur des messages (train officiel)", x=0.01, ha="left", fontweight="bold", color=INK
    )
    return _save(fig, path)


def cooccurrence_figure(
    df: pd.DataFrame, categories: list[str], intents: list[str], path: Path
) -> str:
    """Heatmap of intent x category counts (sequential single hue)."""
    table = pd.crosstab(df["intent"], df["category"]).reindex(
        index=intents, columns=categories, fill_value=0
    )
    fig, ax = plt.subplots(figsize=(7.5, 13))
    im = ax.imshow(table.to_numpy(), aspect="auto", cmap=SEQ_CMAP, interpolation="nearest")
    ax.set_xticks(range(len(categories)), categories, rotation=45, ha="right", fontsize=7)
    ax.set_yticks(range(len(intents)), intents, fontsize=6.5)
    ax.grid(False)
    cbar = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cbar.set_label("messages")
    ax.set_title("Co-occurrence intention × catégorie (train officiel)", loc="left")
    return _save(fig, path)


def crosstab_pct_figure(df: pd.DataFrame, row: str, col: str, title: str, path: Path) -> str:
    """Heatmap of row-normalised percentages for two categorical columns."""
    table = pd.crosstab(df[row], df[col], normalize="index") * 100
    fig, ax = plt.subplots(figsize=(1.0 * len(table.columns) + 3, 0.35 * len(table) + 1.2))
    ax.imshow(table.to_numpy(), aspect="auto", cmap=SEQ_CMAP, vmin=0, vmax=100)
    ax.set_xticks(range(len(table.columns)), table.columns.astype(str))
    ax.set_yticks(range(len(table.index)), table.index.astype(str))
    ax.grid(False)
    for i in range(table.shape[0]):
        for j in range(table.shape[1]):
            v = float(table.to_numpy()[i, j])
            ax.text(
                j,
                i,
                f"{v:.0f}",
                ha="center",
                va="center",
                fontsize=7,
                color="white" if v > 55 else INK,
            )
    ax.set_title(title, loc="left")
    return _save(fig, path)


# --- Markdown helpers --------------------------------------------------------


def md_table(rows: list[dict[str, Any]]) -> str:
    """Render a list of dicts as a Markdown table."""
    if not rows:
        return "_(aucune ligne)_\n"
    cols = list(rows[0].keys())
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        cells = []
        for c in cols:
            v = r[c]
            cells.append(("✅" if v else "⚠️") if isinstance(v, bool) else str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def dist_rows(frames: dict[str, pd.DataFrame], column: str) -> list[dict[str, Any]]:
    """Distribution (%) of ``column`` side by side for several splits."""
    values = sorted({str(v) for df in frames.values() for v in df[column].unique()})
    rows = []
    for v in values:
        row: dict[str, Any] = {column: v}
        for name, df in frames.items():
            share = (df[column].astype(str) == v).mean() * 100
            row[f"{name} (%)"] = round(float(share), 1)
        rows.append(row)
    return rows


def run_eda(paths: Paths, config: dict[str, Any]) -> dict[str, Any]:
    """Pipeline stage: write the EDA report to ``reports/eda``."""
    _style()
    ecfg = config["eda"]
    out = paths.reports / "eda"
    fig_dir = out / "figures"
    taxonomy = load_taxonomy(paths.raw / "telecom_taxonomy.json")

    raw = {s: read_jsonl(paths.raw / f"{s}.jsonl") for s in ("train", "test")}
    final = {s: read_jsonl(paths.processed / f"{s}.jsonl") for s in ("train", "val", "test")}

    stats = {f"raw_{k}": summarize(v) for k, v in raw.items()}
    stats.update({f"final_{k}": summarize(v) for k, v in final.items()})
    checks = {
        s: compare_reference(stats[f"raw_{s}"], ecfg["reference"][s], ecfg["tolerance_points"])
        for s in ("train", "test")
    }

    tr = raw["train"]
    figs = {
        "script": bar_figure(
            tr["script"].value_counts(), "Script (train officiel)", fig_dir / "script.png"
        ),
        "category": bar_figure(
            tr["category"].value_counts(),
            "Catégories (train officiel)",
            fig_dir / "category.png",
            horizontal=True,
        ),
        "intent": bar_figure(
            tr["intent"].value_counts(),
            "Intentions (train officiel)",
            fig_dir / "intent.png",
            horizontal=True,
        ),
        "product": bar_figure(
            tr["product"].value_counts(),
            "Produits (train officiel)",
            fig_dir / "product.png",
            horizontal=True,
        ),
        "urgency": bar_figure(
            tr["urgency"].value_counts().sort_index(),
            "Urgence (train officiel)",
            fig_dir / "urgency.png",
        ),
        "needs_human": bar_figure(
            tr["needs_human"].value_counts().sort_index(),
            "needs_human (train officiel)",
            fig_dir / "needs_human.png",
        ),
        "generator": bar_figure(
            tr["generator"].value_counts(), "Générateur (train officiel)", fig_dir / "generator.png"
        ),
        "round": bar_figure(
            tr["round"].value_counts().sort_index(), "Ronde (train officiel)", fig_dir / "round.png"
        ),
        "length": length_figure(tr, fig_dir / "length.png"),
        "cooccurrence": cooccurrence_figure(
            tr,
            list(taxonomy.categories),
            taxonomy.intents,
            fig_dir / "cooccurrence_intent_category.png",
        ),
        "urgency_needs_human": crosstab_pct_figure(
            tr,
            "urgency",
            "needs_human",
            "needs_human selon l'urgence (% par ligne)",
            fig_dir / "urgency_needs_human.png",
        ),
        "category_product": crosstab_pct_figure(
            tr,
            "category",
            "product",
            "Produit selon la catégorie (% par ligne)",
            fig_dir / "category_product.png",
        ),
    }

    # Heuristic script detector vs labels (informative only).
    det = tr["text"].map(detect_script)
    detector = pd.crosstab(tr["script"], det.rename("détecté"))
    detector_acc = round(float((det == tr["script"]).mean()), 4)

    per_intent = tr["intent"].value_counts()
    rare = {
        "needs_human (%)": stats["raw_train"]["needs_human_pct"],
        "urgence 3 (%)": stats["raw_train"]["urgency_pct"].get("3", 0.0),
        "produit unknown (%)": stats["raw_train"]["product_unknown_pct"],
        "non_telecom (%)": stats["raw_train"]["non_telecom_pct"],
    }

    s_tr, s_te = stats["raw_train"], stats["raw_test"]
    lines = [
        "# Rapport d'EDA — Jev-Darija Telecom",
        "",
        "> Rapport généré automatiquement par `dvc repro` (étape `eda`). "
        "Ne pas modifier à la main.",
        "> Données **synthétiques** (mballouch/jev-darija-telecom, CC BY 4.0, Mohamed Ballouch).",
        "",
        "## 1. Contrôle croisé avec le Tableau 5 du cahier des charges",
        "",
        f"Tolérance : ± {ecfg['tolerance_points']} point (pourcentages), "
        "mesures sur les fichiers bruts.",
        "",
        "### Train officiel",
        "",
        md_table(checks["train"]),
        "### Test officiel",
        "",
        md_table(checks["test"]),
        "## 2. Vue d'ensemble",
        "",
        md_table(
            [
                {
                    "split": "train officiel",
                    "lignes": s_tr["rows"],
                    "intentions": s_tr["intents"],
                    "catégories": s_tr["categories"],
                    "min/intention": s_tr["per_intent_min"],
                    "max/intention": s_tr["per_intent_max"],
                    "ratio déséquilibre": s_tr["imbalance_ratio_intent"],
                },
                {
                    "split": "test officiel",
                    "lignes": s_te["rows"],
                    "intentions": s_te["intents"],
                    "catégories": s_te["categories"],
                    "min/intention": s_te["per_intent_min"],
                    "max/intention": s_te["per_intent_max"],
                    "ratio déséquilibre": s_te["imbalance_ratio_intent"],
                },
            ]
            + [
                {
                    "split": f"final {k}",
                    "lignes": stats[f"final_{k}"]["rows"],
                    "intentions": stats[f"final_{k}"]["intents"],
                    "catégories": stats[f"final_{k}"]["categories"],
                    "min/intention": stats[f"final_{k}"]["per_intent_min"],
                    "max/intention": stats[f"final_{k}"]["per_intent_max"],
                    "ratio déséquilibre": stats[f"final_{k}"]["imbalance_ratio_intent"],
                }
                for k in ("train", "val", "test")
            ]
        ),
        "## 3. Déséquilibres à surveiller (train officiel)",
        "",
        md_table([{"indicateur": k, "valeur": v} for k, v in rare.items()]),
        "Conséquences pour la suite : métriques macro-F1 en plus de l'exactitude, seuil "
        "needs_human choisi sur la courbe précision-rappel, attention particulière à "
        "l'urgence 3 (classe rare et critique).",
        "",
        "Intentions les moins représentées : "
        + ", ".join(f"`{i}` ({n})" for i, n in per_intent.nsmallest(5).items()),
        "",
        "## 4. Distributions",
        "",
        "### Script",
        "",
        md_table(
            dist_rows(
                {"train": final["train"], "val": final["val"], "test": final["test"]}, "script"
            )
        ),
        f"![script](figures/{figs['script']})",
        "",
        "### Catégories",
        "",
        md_table(
            dist_rows(
                {"train": final["train"], "val": final["val"], "test": final["test"]}, "category"
            )
        ),
        f"![catégories](figures/{figs['category']})",
        "",
        "### Intentions",
        "",
        f"![intentions](figures/{figs['intent']})",
        "",
        "### Produit",
        "",
        md_table(
            dist_rows(
                {"train": final["train"], "val": final["val"], "test": final["test"]}, "product"
            )
        ),
        f"![produits](figures/{figs['product']})",
        "",
        "### Urgence et needs_human",
        "",
        md_table(
            dist_rows(
                {"train": final["train"], "val": final["val"], "test": final["test"]}, "urgency"
            )
        ),
        md_table(
            dist_rows(
                {"train": final["train"], "val": final["val"], "test": final["test"]}, "needs_human"
            )
        ),
        f"![urgence](figures/{figs['urgency']})",
        f"![needs_human](figures/{figs['needs_human']})",
        f"![urgence x needs_human](figures/{figs['urgency_needs_human']})",
        "",
        "### Générateur et ronde",
        "",
        md_table(
            dist_rows(
                {"train": final["train"], "val": final["val"], "test": final["test"]}, "generator"
            )
        ),
        f"![générateur](figures/{figs['generator']})",
        f"![ronde](figures/{figs['round']})",
        "",
        "## 5. Longueurs",
        "",
        md_table(
            [
                {
                    "split": k,
                    "moyenne": stats[k]["length_mean"],
                    "médiane": stats[k]["length_median"],
                    "min": stats[k]["length_min"],
                    "max": stats[k]["length_max"],
                }
                for k in ("raw_train", "raw_test", "final_train", "final_val", "final_test")
            ]
        ),
        f"![longueurs](figures/{figs['length']})",
        "",
        "## 6. Co-occurrences",
        "",
        "Chaque intention appartient à une seule catégorie (diagonale par blocs) :",
        "",
        f"![co-occurrence](figures/{figs['cooccurrence']})",
        "",
        f"![catégorie x produit](figures/{figs['category_product']})",
        "",
        "## 7. Détecteur de script heuristique (informatif)",
        "",
        f"Exactitude sur le train officiel : **{detector_acc:.2%}**. La frontière arabizi / "
        "mixte est floue dans les données (beaucoup de messages arabizi contiennent des mots "
        "français isolés) ; le détecteur n'est utilisé que pour le contrôle de cohérence.",
        "",
        md_table(
            [
                {"label": str(idx), **{str(c): int(v) for c, v in row.items()}}
                for idx, row in detector.iterrows()
            ]
        ),
    ]
    write_text("\n".join(lines) + "\n", out / "README.md")
    summary = {"stats": stats, "table5_checks": checks, "script_detector_accuracy": detector_acc}
    write_json(summary, out / "eda.json")
    failed = [r for s in checks.values() for r in s if not r["ok"]]
    if failed:
        log.warning("Écarts avec le Tableau 5 : %s", failed)
    return summary
