"""TF-IDF baseline: character n-grams (2–5) + linear SVM, one classifier per task.

The intent classifier predicts one of the 75 intents; the category is derived
from it through the taxonomy, so category and intent are always consistent.
Product, urgency and needs_human have their own classifiers on the same features.

Hyperparameters are fixed in ``configs/train.yaml`` (no tuning on the test set).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC

from darijacare.config import Paths
from darijacare.data.taxonomy import load_taxonomy
from darijacare.io import read_jsonl, write_json
from darijacare.nlu import tracking
from darijacare.nlu.metrics import headline_metrics, metrics_by_group

log = logging.getLogger(__name__)

LABEL_TASKS = ("intent", "product", "urgency", "needs_human")


@dataclass
class TfidfBaseline:
    """Shared TF-IDF features + one LinearSVC per task."""

    params: dict[str, Any]
    intent_to_category: dict[str, str]

    def __post_init__(self) -> None:
        p = self.params
        self.vectorizer = TfidfVectorizer(
            analyzer=p.get("analyzer", "char_wb"),
            ngram_range=tuple(p.get("ngram_range", (2, 5))),
            min_df=p.get("min_df", 2),
            max_features=p.get("max_features"),
            sublinear_tf=p.get("sublinear_tf", True),
            dtype=np.float64,
        )
        self.models: dict[str, LinearSVC | DummyClassifier] = {}

    def fit(self, texts: pd.Series, labels: pd.DataFrame) -> TfidfBaseline:
        """Fit the vectoriser and one classifier per task."""
        x = self.vectorizer.fit_transform(texts.tolist())
        for task in LABEL_TASKS:
            y = labels[task].astype(str)
            clf: LinearSVC | DummyClassifier
            if y.nunique() < 2:  # a single class: LinearSVC refuses to fit
                clf = DummyClassifier(strategy="most_frequent").fit(x, y)
                self.models[task] = clf
                continue
            balanced = task in self.params.get("balanced_tasks", [])
            clf = LinearSVC(
                C=self.params.get("C", 0.5),
                class_weight="balanced" if balanced else None,
                random_state=self.params.get("seed", 42),
                max_iter=self.params.get("max_iter", 5000),
            )
            clf.fit(x, y)
            self.models[task] = clf
        return self

    def predict(self, texts: pd.Series) -> pd.DataFrame:
        """Predict every task; ``category`` is derived from the predicted intent."""
        x = self.vectorizer.transform(texts.tolist())
        out = pd.DataFrame(index=texts.index)
        for task, clf in self.models.items():
            out[task] = clf.predict(x)
        out["category"] = out["intent"].map(self.intent_to_category)
        out["urgency"] = out["urgency"].astype(int)
        out["needs_human"] = out["needs_human"].map({"True": True, "False": False})
        return out


def run_baseline(paths: Paths, config: dict[str, Any]) -> dict[str, Any]:
    """Train on ``train``, report on ``val`` and ``test``, log everything to MLflow."""
    params = {**config["baseline"], "seed": config["seed"]}
    text_col = params.get("text_column", "text_norm")
    taxonomy = load_taxonomy(paths.raw / "telecom_taxonomy.json")
    train = read_jsonl(paths.processed / "train.jsonl")
    model = TfidfBaseline(params, taxonomy.intent_to_category).fit(train[text_col], train)

    report: dict[str, Any] = {"params": params}
    with tracking.start_run("baseline_tfidf_svm", params, paths) as run:
        for split in ("val", "test"):
            df = read_jsonl(paths.processed / f"{split}.jsonl")
            pred = model.predict(df[text_col])
            metrics = headline_metrics(df, pred)
            report[split] = {
                "overall": metrics,
                "by_script": metrics_by_group(df, pred, "script"),
            }
            run.log_metrics({f"{split}_{k}": v for k, v in metrics.items()})
            log.info("[%s] intention bout en bout %.4f", split, metrics["intent_end_to_end"])
        out = paths.reports / "nlu" / "baseline.json"
        write_json(report, out)
        run.log_artifact(out)
    return report
