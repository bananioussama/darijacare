"""TF-IDF + linear SVM baseline on a tiny synthetic set."""

from __future__ import annotations

import pandas as pd

from darijacare.nlu.baseline import TfidfBaseline
from darijacare.nlu.metrics import headline_metrics
from tests.conftest import make_row

I2C = {
    "balance_check": "prepaid_credit",
    "recharge_how": "prepaid_credit",
    "non_telecom": "out_of_scope",
}


def _df() -> pd.DataFrame:
    rows = []
    templates = {
        "balance_check": ["ch7al b9a f solde {}", "bghit n3ref rasid dyali {}"],
        "recharge_how": ["kifach nchargi {} dh", "fin nchri recharge {}"],
        "non_telecom": ["chkoun rbe7 match {}", "ch7al jat taxi {}"],
    }
    i = 0
    for intent, tpls in templates.items():
        for k in range(12):
            text = tpls[k % 2].format(k * 10)
            rows.append(make_row(i, text, intent=intent, urgency=k % 2, needs_human=k % 3 == 0))
            i += 1
    return pd.DataFrame(rows)


def test_baseline_fits_and_predicts_consistent_labels() -> None:
    df = _df()
    params = {
        "ngram_range": [2, 4],
        "min_df": 1,
        "C": 1.0,
        "seed": 0,
        "balanced_tasks": ["needs_human"],
    }
    model = TfidfBaseline(params, I2C).fit(df["text"], df)
    pred = model.predict(df["text"])
    assert set(pred.columns) >= {"intent", "category", "product", "urgency", "needs_human"}
    assert (pred["category"] == pred["intent"].map(I2C)).all()
    assert pred["needs_human"].isin([True, False]).all()
    assert pred["urgency"].dtype.kind == "i"
    assert headline_metrics(df, pred)["intent_end_to_end"] == 1.0
