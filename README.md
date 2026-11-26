# remediation-guardrails

**P03 — Guardrails for LLM-Driven Auto-Remediation: A Safety Evaluation**

Project Elective (4 credits), Aug–Dec 2026 · Dept. of CSE, IIIT Bangalore
Faculty: Prof. B. Thangaraju

---

## What this is

A measurement study, not a product.

Letting an LLM propose *and execute* remediation actions in response to production alerts
is attractive but dangerous — models hallucinate targets, over-reach, oscillate, and can be
prompt-injected through log data. The publishable question is not whether it works in a
demo, but **how often it acts unsafely, and how much a deterministic verification gate
reduces that — at what cost to its ability to actually fix things.**

We build a seeded fault-injection testbed, put a deterministic verification gate between
the model's proposal and its execution, and measure the safety/utility tradeoff.

## Start here

**[docs/00-problem-and-plan.md](docs/00-problem-and-plan.md)** — problem statement,
architecture, gate design, fault catalogue, metrics, experiment design, and the phased
build plan. Read Part 1 before writing any code.

## Design in one paragraph

The model never acts directly. It emits a **typed proposal** drawn from a fixed action
catalogue. A deterministic gate — ordinary code, no model — checks that proposal against
ground-truth state via six independent checks (target implication, signal→action policy,
blast radius, oscillation, action budget, evidence freshness) and approves, blocks, or
escalates. Only approved proposals execute. Everything is logged; the logs are the dataset.

## Status

| Phase | | |
|---|---|---|
| 0 | Repo skeleton, config, log schema, CI | done |
| 1 | Simulator core | done (determinism test in CI) |
| 2 | Observer, alerts, context builder | done |
| 3 | Action catalogue + executor | done (one test per action) |
| 4 | Mock proposers | done (5 mocks reproduce their failure mode) |
| 5 | **Verification gate** | done (C1–C6, shadow mode, validated on all mocks) |
| 6 | LLM proposer | done (Ollama, schema-constrained JSON, seeded, cached) |
| 7 | Fault catalogue + full runner | done (32 pre-registered scenarios; tag `freeze-v1`) |
| 8 | Analysis + stats | done (`rg analyze` regenerates every number) |
| 9 | Docker validation *(optional)* | not done |
| 10 | Experiments + paper | done: Llama-3.2-3B (3 seeds main, 2 seeds ablations) and Qwen2.5-7B (1 seed, main) written up |
| 11 | Reviewer-proofing (post hoc) | done: simpler-gate baselines (deny-list A3d/A1d, policy-only A3p), gate-aware injection family I (`configs/scenarios_adaptive.yaml`), scenario-level sign tests, exact zero-event bounds |

The inter-rater check is done: κ = 0.78 on the independent first pass, 0.95 after the
rater re-checked one misread rule (both reported; see `docs/03-threats-to-validity.md`).

Still open before submission:
- the author list and order, and the target venue;
- the repository URL in the paper's artifact statement (for double-blind review, set
  `\anontrue` in `paper/main.tex` and use an anonymised mirror);
- optionally, one stronger model (e.g. `qwen2.5:32b`, one seed of the main arms).

## Reproduce

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
.venv/bin/pytest -q                                   # 275 tests
.venv/bin/rg validate                                 # configs + catalogue hash
.venv/bin/rg run --arm A0,A1,A1g,A1d,M-correct-deny --seeds 0-14   # non-LLM arms
ollama pull llama3.2 && ollama pull qwen2.5:7b
.venv/bin/rg run --arm A2,A3,A2b,A4,A3d,A3p --model llama3.2-3b --seeds 0-2 --workers 2
# supplementary, post hoc: gate-aware injection (family I), logged to results/raw_adaptive/
.venv/bin/rg run --arm M-correct,M-correct-gated,M-injection_follower,M-injection_follower-gated \
    --seeds 0-14 --catalogue adaptive
.venv/bin/rg run --arm A2,A2b,A3,A4 --model llama3.2-3b --seeds 0-2 --catalogue adaptive
.venv/bin/rg analyze                                  # tables, figures, paper/numbers.tex
cd paper && latexmk -pdf main.tex
```

## Layout

| Path | What |
|---|---|
| `src/rg/sim/` | Seeded cluster simulator (ground truth) |
| `src/rg/observe/` | Alerts, logs, metric windows, diagnostics, the proposer's context |
| `src/rg/actions/` | Typed action catalogue and effect model |
| `src/rg/propose/` | Random, runbook, five mocks, LLM proposer |
| `src/rg/gate/` | The verification gate C1–C6 |
| `src/rg/faults/` | Episode setup and the pre-registered labeller |
| `src/rg/harness/` | Episode loop and resumable runner |
| `src/rg/analysis/` | Metrics, cluster bootstrap, McNemar, tables, figures, inter-rater tool |
| `configs/` | Topology, gate policy, arms, models, **scenarios.yaml (frozen)** |
| `docs/` | Plan, literature survey, phase plan, fault catalogue, threats, log schema |
| `results/raw/` | Episode JSONL (git-ignored, regenerable) |
| `results/derived/` | Summary tables (tracked) |
| `paper/` | IEEE conference paper; tables/figures/numbers are generated |

## Team

| Sub-role | Responsibility |
|---|---|
| Testbed & Implementation | Fault testbed, LLM integration, verification gate (Phases 0–6) |
| Measurement & Analysis | Fault catalogue, unsafe-action and recovery measurement (Phases 7–8) |
| Related Work & Writing | Related work on autonomic/LLM ops, write-up (from week 1) |

Fault-catalogue labelling is kept **independent** of gate implementation — labels are
pre-registered and frozen before any model runs, so the safety grading isn't tuned to the
implementation being graded.
