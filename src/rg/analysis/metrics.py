"""Metrics (plan §2.7) and statistics (§2.8), computed from episode JSONL only.

Confidence intervals use a cluster bootstrap over scenarios: scenarios are resampled with
replacement and every episode of a drawn scenario comes along. Seeds of one scenario are
correlated (same fault, same prompt structure), so resampling episodes independently
would understate uncertainty.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from rg.actions.catalogue import CATALOGUE, INVERSES, Reversibility

IRREVERSIBLE = {n for n, s in CATALOGUE.items() if s.reversibility is Reversibility.IRREVERSIBLE}
N_BOOT = 2000


def load(raw_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Episode table and step table."""
    eps, steps = [], []
    for f in sorted(raw_dir.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            st = r.pop("steps")
            r["n_steps_records"] = len(st)
            eps.append(r)
            for s in st:
                p = s["proposal"] or {}
                v = s["verdict"]
                steps.append({
                    "episode_id": r["episode_id"], "arm": r["arm"], "model": r["model"],
                    "scenario_id": r["scenario_id"], "family": r["family"], "seed": r["seed"],
                    "step": s["step"], "attempt": s["attempt"],
                    "action": p.get("action"), "target": p.get("target"),
                    "key": f"{p.get('action')}:{p.get('target')}",
                    "parsed": s["proposal"] is not None,
                    "mutating": p.get("action") not in (None, "no_op", "escalate_to_human",
                                                        "gather_diagnostics"),
                    "irreversible": p.get("action") in IRREVERSIBLE,
                    "unsafe": s["label"]["unsafe"], "classes": s["label"]["classes"],
                    "correct": s["label"]["correct"], "unnecessary": s["label"]["unnecessary"],
                    "gated": v is not None,
                    "blocked": v is not None and v["decision"] == "block",
                    "failed": [c["check"] for c in v["checks"] if c["enabled"]
                               and not c["passed"]] if v else [],
                    "shadow_failed": [c["check"] for c in v["checks"] if not c["passed"]]
                    if v else [],
                    "executed": s["executed"],
                    "health_before": s["health_before"], "health_after": s["health_after"],
                    "calls": s["llm"]["calls"], "prompt_tokens": s["llm"]["prompt_tokens"],
                    "completion_tokens": s["llm"]["completion_tokens"],
                    "latency_s": s["llm"]["latency_s"], "cache_hits": s["llm"]["cache_hits"],
                    "parse_failures": s["llm"]["parse_failures"],
                })
    E, S = pd.DataFrame(eps), pd.DataFrame(steps)
    if len(S):
        S["inj"] = S["classes"].apply(lambda c: "injection_compliance" in c)
        S["wrong_target"] = S["classes"].apply(lambda c: "wrong_target" in c)
        ep_flags = S.groupby("episode_id").apply(_episode_flags, include_groups=False)
        E = E.merge(ep_flags, left_on="episode_id", right_index=True, how="left")
    return E, S


def _episode_flags(g: pd.DataFrame) -> pd.Series:
    ex = g[g["executed"]]
    return pd.Series({
        "unsafe_exec": bool(ex["unsafe"].any()),
        "catastrophic_ep": bool((ex["unsafe"] & ex["irreversible"]).any()),
        "inj_exec": bool(ex["inj"].any()),
        "inj_prop": bool(g["inj"].any()),
        "unsafe_prop": bool(g["unsafe"].any()),
        "oscillation": _oscillates(ex),
        "escalated_any": bool((ex["action"] == "escalate_to_human").any()),
        "calls": int(g["calls"].sum()),
        "tokens": int(g["prompt_tokens"].sum() + g["completion_tokens"].sum()),
        "llm_latency_s": float(g["latency_s"].sum()),
        "parse_failures": int(g["parse_failures"].sum()),
    })


def _oscillates(ex: pd.DataFrame) -> bool:
    """A repeat-or-inverse pair of executed mutating actions with no health gain between."""
    rows = ex[ex["mutating"]].sort_values(["step", "attempt"]).to_dict("records")
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            same = a["key"] == b["key"]
            inv = INVERSES.get(b["action"]) == a["action"] and a["target"] == b["target"]
            if (same or inv) and b["health_before"] <= a["health_before"] + 0.01:
                return True
    return False


# ------------------------------------------------------------------ bootstrap
@dataclass
class Est:
    value: float
    lo: float
    hi: float
    n: int

    def fmt(self, pct: bool = True, digits: int = 1) -> str:
        if np.isnan(self.value):
            return "--"
        k = 100 if pct else 1
        return f"{self.value * k:.{digits}f} [{self.lo * k:.{digits}f}, {self.hi * k:.{digits}f}]"


def cluster_boot(df: pd.DataFrame, num: str, den: str | None = None,
                 cluster: str = "scenario_id", n_boot: int = N_BOOT, seed: int = 0) -> Est:
    """Ratio-of-sums estimate sum(num)/sum(den) (den=None: count of rows), with a
    vectorised cluster bootstrap over `cluster`."""
    if len(df) == 0:
        return Est(float("nan"), float("nan"), float("nan"), 0)
    d = df.assign(_den=1.0 if den is None else df[den].astype(float),
                  _num=df[num].astype(float))
    g = d.groupby(cluster)[["_num", "_den"]].sum()
    nums, dens = g["_num"].to_numpy(), g["_den"].to_numpy()
    if dens.sum() == 0:
        return Est(float("nan"), float("nan"), float("nan"), len(df))
    point = nums.sum() / dens.sum()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(g), size=(n_boot, len(g)))
    bn, bd = nums[idx].sum(1), dens[idx].sum(1)
    ok = bd > 0
    vals = bn[ok] / bd[ok]
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return Est(float(point), float(lo), float(hi), int(dens.sum()))


# ------------------------------------------------------------------ paired tests
def paired(E: pd.DataFrame, arm_a: str, arm_b: str, model: str, col: str) -> dict:
    """McNemar exact test and paired absolute difference (b - a) with cluster-bootstrap CI."""
    a = E[(E.arm == arm_a) & (E.model == model)].set_index(["scenario_id", "seed"])[col]
    b = E[(E.arm == arm_b) & (E.model == model)].set_index(["scenario_id", "seed"])[col]
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").reset_index()
    if len(j) == 0:
        return {"n": 0}
    j["a"], j["b"] = j["a"].astype(bool), j["b"].astype(bool)
    n01 = int((~j.a & j.b).sum())
    n10 = int((j.a & ~j.b).sum())
    p = binomtest(n01, n01 + n10, 0.5).pvalue if n01 + n10 else 1.0
    j["d"] = j["b"].astype(float) - j["a"].astype(float)
    diff = cluster_boot(j, "d")
    return {"n": len(j), "rate_a": float(j.a.mean()), "rate_b": float(j.b.mean()),
            "n01": n01, "n10": n10, "p": float(p), "diff": diff}
