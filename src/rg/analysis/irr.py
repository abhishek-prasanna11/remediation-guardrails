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

from fractions import Fraction

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
    S["prop"] = S.apply(lambda r: f"{r.action}({r.target if isinstance(r.target, str) else ''})", axis=1)
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
    """Cohen's kappa, computed in exact fractions so a value such as 0.775 is not
    printed as 0.77 through floating-point error."""
    a, b = [int(x) for x in a], [int(x) for x in b]
    n = len(a)
    po = Fraction(sum(x == y for x, y in zip(a, b, strict=True)), n)
    pa, pb = Fraction(sum(a), n), Fraction(sum(b), n)
    pe = pa * pb + (1 - pa) * (1 - pb)
    return float((po - pe) / (1 - pe)) if pe < 1 else 1.0


# `rater_unsafe` is the rater's independent first pass. `rater_revised` (optional) holds
# their answers after the disagreements were discussed; it is reported next to, never
# instead of, the first pass.
PASSES = {"rater_unsafe": "first pass", "rater_revised": "after discussion"}


def score() -> None:
    j = pd.read_csv(SHEET).merge(pd.read_csv(KEY), on="row")
    for col, name in PASSES.items():
        if col not in j:
            continue
        rated = j[j[col].astype(str).str.strip().isin(["0", "1"])]
        if not len(rated):
            print(f"{name}: no rows rated yet")
            continue
        r, u = rated[col].astype(int), rated.unsafe.astype(int)
        print(f"{name}: rated rows {len(rated)}; raw agreement {(r == u).mean():.3f}; "
              f"Cohen's kappa {kappa(r, u):.3f}")
        print(pd.crosstab(u.rename("mechanical"), r.rename("rater")))
