"""Inter-rater agreement on the safety labels (plan §1.6).

  rg irr export   writes results/derived/irr_sheet.csv: a stratified random sample of
                  distinct (scenario, proposal) pairs, with the scenario description and
                  the proposal but WITHOUT the mechanical label. A teammate who did not
                  write the gate fills `rater_unsafe` (0/1) for each row, using only
                  docs/02-fault-catalogue.md §"Unsafe" definitions.
  rg irr score    reads the filled sheet and reports Cohen's kappa between the rater and
                  the mechanical labeller, plus the confusion matrix.
"""

from __future__ import annotations

import pandas as pd

from rg.analysis.metrics import load
from rg.config import ROOT, load_scenarios

RAW = ROOT / "results" / "raw"
SHEET = ROOT / "results" / "derived" / "irr_sheet.csv"
KEY = ROOT / "results" / "derived" / "irr_key.csv"  # mechanical labels, kept apart
N_PER_STRATUM = 40


def export() -> None:
    _, S = load(RAW)
    S = S[S.parsed].copy()
    S["prop"] = S.apply(lambda r: f"{r.action}({r.target or ''})", axis=1)
    distinct = S.drop_duplicates(["scenario_id", "prop"])
    parts = []
    for unsafe in (True, False):
        g = distinct[distinct.unsafe == unsafe]
        parts.append(g.sample(min(N_PER_STRATUM, len(g)), random_state=0))
    sample = pd.concat(parts).sample(frac=1, random_state=1).reset_index(drop=True)
    scen = load_scenarios()
    sample["scenario"] = sample.scenario_id.map(lambda s: scen[s].title)
    sample["family"] = sample.scenario_id.map(lambda s: scen[s].family)
    sample["row"] = range(1, len(sample) + 1)
    sheet = sample[["row", "scenario_id", "family", "scenario", "prop"]].copy()
    sheet["rater_unsafe"] = ""
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    sheet.to_csv(SHEET, index=False)
    sample[["row", "unsafe"]].to_csv(KEY, index=False)
    print(f"wrote {len(sheet)} rows to {SHEET} (fill rater_unsafe with 0/1); key in {KEY}")


def kappa(a: pd.Series, b: pd.Series) -> float:
    a, b = a.astype(int), b.astype(int)
    po = float((a == b).mean())
    pe = float(a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean()))
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def score() -> None:
    sheet = pd.read_csv(SHEET)
    key = pd.read_csv(KEY)
    j = sheet.merge(key, on="row")
    j = j[j.rater_unsafe.astype(str).str.strip().isin(["0", "1"])]
    if not len(j):
        print("no rows rated yet")
        return
    j["rater"] = j.rater_unsafe.astype(int)
    k = kappa(j.rater, j.unsafe)
    print(f"rated rows: {len(j)}; raw agreement {(j.rater == j.unsafe.astype(int)).mean():.3f}; "
          f"Cohen's kappa {k:.3f}")
    print(pd.crosstab(j.unsafe.rename("mechanical"), j.rater.rename("rater")))
