"""Runner: `rg run --arm A3 --model llama3.2-3b --seeds 0-14`.

Sweeps every scenario x seed for one (arm, model) cell and appends one JSONL line per
episode to results/raw/{arm}__{model}.jsonl. Resumable: episodes already in the file are
skipped, so an interrupted run continues where it stopped.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rg.config import (
    ROOT,
    ArmConfig,
    catalogue_sha,
    load_arms,
    load_models,
    load_scenarios,
    scenarios_path,
)
from rg.gate.gate import make_gate
from rg.harness.episode import run_episode
from rg.propose.base import MOCKS, Proposer, RandomProposer, RunbookProposer

RAW = ROOT / "results" / "raw"


def make_proposer(arm: ArmConfig, model_name: str) -> Proposer:
    if arm.proposer == "random":
        return RandomProposer()
    if arm.proposer == "runbook":
        return RunbookProposer()
    if arm.proposer == "mock":
        return MOCKS[arm.mock]()
    from rg.propose.llm import LLMProposer

    return LLMProposer(load_models()[model_name], prompt_variant=arm.prompt)


def raw_dir(catalogue: str = "main") -> Path:
    """Supplementary catalogues log to their own directory, so the main analysis never
    mixes them with the pre-registered scenarios."""
    return RAW if catalogue == "main" else ROOT / "results" / f"raw_{catalogue}"


def out_path(arm: str, model: str, catalogue: str = "main") -> Path:
    return raw_dir(catalogue) / f"{arm}__{model}.jsonl"


def done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text().splitlines():
        if line.strip():
            out.add(json.loads(line)["episode_id"])
    return out


def parse_seeds(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def run_cell(arm_name: str, model: str, seeds: list[int], scenarios: list[str] | None = None,
             workers: int = 1, verbose: bool = True, catalogue: str = "main") -> Path:
    arm = load_arms()[arm_name]
    if arm.proposer != "llm":
        model = "none"
    scen = load_scenarios(scenarios_path(catalogue))
    ids = scenarios or sorted(scen)
    sha = catalogue_sha(scenarios_path(catalogue))
    path = out_path(arm_name, model, catalogue)
    path.parent.mkdir(parents=True, exist_ok=True)
    done = done_ids(path)
    todo = [(sid, s) for sid in ids for s in seeds
            if f"{arm_name}/{model}/{sid}/{s}" not in done]
    lock = threading.Lock()

    def one(job: tuple[str, int]) -> str:
        sid, seed = job
        gate = make_gate(arm.gate_kind, arm.disabled_checks) if arm.gate else None
        rec = run_episode(scen[sid], seed, arm, make_proposer(arm, model), gate,
                          model=model, cat_sha=sha)
        line = rec.model_dump_json()
        with lock, path.open("a") as f:
            f.write(line + "\n")
        return f"{rec.episode_id} {rec.outcome} resolved={rec.resolved}"

    with ThreadPoolExecutor(max(1, workers)) as ex:
        futs = [ex.submit(one, j) for j in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            msg = fut.result()
            if verbose and (i % 25 == 0 or i == len(todo)):
                print(f"[{arm_name}/{model}] {i}/{len(todo)} {msg}", flush=True)
    return path
