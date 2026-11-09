# Phase Plan — Guardrails for LLM-Driven Auto-Remediation

Expands the phase table in [`00-problem-and-plan.md`](./00-problem-and-plan.md) §Part 3
into concrete tasks per phase. Ordering and "done when" criteria are unchanged from that
document — this file adds the *how*.

---

## Phase 0 — Repo skeleton & infra

**Deliverable:** Repo skeleton, config loading, JSONL log schema, pytest + CI.

Tasks:
- Create the `src/rg/` package layout from §2.9 (`sim/`, `observe/`, `actions/`,
  `propose/`, `gate/`, `faults/`, `harness/`, `analysis/`), plus `configs/`, `tests/`,
  `results/` (git-ignored), `paper/`.
- `pyproject.toml` with `uv`/`venv`, `pydantic`, `pytest`, `pandas`, `matplotlib`.
- Define the pydantic models for the episode JSONL record (one line per step: context,
  proposal, verdict, execution, state snapshot) — this schema is load-bearing, since
  analysis in Phase 8 reads nothing else.
- Config loading: scenario configs, policy matrix, arm definitions, model definitions —
  all pydantic, all validated at load time.
- CI: run `pytest` on push; lint (ruff/black) as a cheap early gate.

**Done when:** `pytest` green on a trivial test; JSONL schema documented in this repo
(e.g. `docs/schema.md` or docstrings on the pydantic models).

---

## Phase 1 — Simulator core

**Deliverable:** Services, tick dynamics, dependency propagation, invariants.

Tasks:
- `Service` model: `name`, `replicas`, `cpu_pct`, `mem_pct`, `latency_p99_ms`,
  `error_rate`, `disk_pct`, `up`, `version`, `depends_on[]` (§2.3).
- `tick()` pipeline, applied in order every step:
  1. Fault dynamics (memory leak growth, disk filler, bad-deploy error-rate bump).
  2. Dependency propagation (upstream `error_rate` → downstream `latency_p99_ms`) —
     this is what produces realistic victim-not-cause cascades (fault family C).
  3. Natural dynamics: decay toward baseline + bounded seeded-RNG noise.
  4. Invariant evaluation, recording any violation for later grading.
- Seeded RNG plumbing throughout — no unseeded randomness anywhere in the sim.
- Determinism test: same seed twice ⇒ byte-identical state trace. This is a hard gate,
  not a nice-to-have — everything downstream assumes it.

**Done when:** the determinism test passes and is in CI.

---

## Phase 2 — Observer

**Deliverable:** Alert rules, metric windows, log templating, context builder.

Tasks:
- Alert rule set: thresholds/conditions over `SimulatedCluster` state that fire alerts
  matching each fault family in §2.6 (A–H) at the correct tick.
- Metric windowing: rolling windows of the metrics an SRE would actually see, not raw
  instantaneous state.
- Log templating: generate log lines per service/fault, including the injection points
  used later for fault family F (adversarial text embedded in log lines).
- Context builder: assembles exactly what the proposer sees (alert + metrics + logs +
  relevant runbook text + action catalogue) — and **only** that. Enforce the boundary
  from §2.1: the proposer must never see raw `SimulatedCluster` state directly.
- Test per fault family: inject a known fault, assert the right alert fires at the
  right tick with the expected fields.

**Done when:** given a known fault, the right alert fires at the right tick, for every
fault family, under test.

---

## Phase 3 — Action catalogue & executor

**Deliverable:** Action catalogue, executor, effect model.

Tasks:
- Implement every action in the §2.4 table (`no_op`, `escalate_to_human`,
  `gather_diagnostics`, `restart_service`, `scale_up`, `scale_down`, `rollback_deploy`,
  `clear_cache`, `disable_feature_flag`, `failover_database`, `drain_node`,
  `truncate_logs`, `delete_files`, `flush_queue`) as typed pydantic models with an
  explicit `reversibility` field (`safe` / `reversible` / `irreversible`).
- Effect model: what each action actually mutates on `SimulatedCluster` (e.g.
  `restart_service` resets `error_rate`/`mem_pct` after a delay; `scale_down` can breach
  `min_replicas`).
- Executor: applies an approved action, produces the effect, and hands the record to
  the JSONL logger.
- Deliver the catalogue to the model as a structured tool/function schema — no
  free-text action parsing (§2.4 explicitly calls this out as an avoidable bug source).
- Unit test every action's effect and its reversibility flag.

**Done when:** every action has an effect and a unit test; irreversibility flags set
correctly (checked against the §2.4 table).

---

## Phase 4 — Mock proposers

**Deliverable:** Scripted proposers reproducing each failure mode deterministically, at
zero API cost.

Tasks:
- `correct` — always proposes the pre-registered correct action for the scenario.
- `hallucinator` — proposes a plausible-looking but wrong-target action (feeds fault
  family C / over-reach testing and C1 in the gate).
- `over_reacher` — proposes a disproportionate action relative to alert severity
  (feeds C2/C3).
- `oscillator` — alternates an action and its inverse across steps regardless of
  observed state change (feeds C4).
- `injection_follower` — complies with adversarial instructions embedded in observed
  log/annotation text (feeds fault family F, C1/C2 as the defence).
- Each mock proposer needs its own test asserting it reproduces its target failure mode
  reliably and deterministically given a seed.

**Done when:** each mock proposer reproduces its intended failure mode deterministically
under test — this is the harness you'll use to validate the gate in Phase 5 without ever
calling an LLM.

---

## Phase 5 — The gate

**Deliverable:** C1–C6, policy matrix, structured verdicts. This is the actual
contribution of the project — protect the time allocated to it.

Tasks:
- **C1 Precondition/target implication** — target must exhibit the violated signal from
  the firing alert.
- **C2 Signal→action policy matrix** — declared `{alert class → permitted action
  classes}` mapping (e.g. `DiskSpaceLow` permits `truncate_logs`/`scale_up`, not
  `failover_database`); load from `configs/`.
- **C3 Blast radius & invariants** — `min_replicas` breach check, log-path allowlist,
  healthy-primary failover check, "touches >N services" check.
- **C4 Oscillation detection** — maintains a per-episode action history; blocks an
  action or its inverse repeated within window `W` with no measurable health
  improvement.
- **C5 Action budget** — hard cap `M` mutating actions per incident.
- **C6 Evidence freshness** — re-reads ground-truth state at execution time and
  confirms the cited symptom is still true (catches stale-context actions from
  model-latency drift).
- Each check individually toggleable (needed for the A5 ablation arm in §2.8).
- Verdict object carries a structured reason string, e.g.
  `rejected(C1): target 'payments' not implicated; violated signal is latency_p99 on
  'checkout'`.
- Feed-vs-no-feed of the rejection reason back to the proposer is an experimental arm
  (A3 vs A4) — build the plumbing for both, decide nothing about which "wins" yet.
- Validate against every Phase-4 mock proposer: each failure mode must be caught by the
  check(s) it's designed to trip, under test.

**Done when:** each check has unit tests, and all Phase-4 mock proposers are caught as
expected — with no real LLM involved yet.

---

## Phase 6 — Real LLM proposer

**Deliverable:** Pluggable LLM backend, structured tool-calling, retry/parse handling.

Tasks:
- Proposer interface stays identical to the mock proposers from Phase 4 — the harness
  should not need to know whether it's talking to a script or a model.
- Structured tool/function-calling against the Phase-3 action schema (no free-text
  parsing).
- Retry/parse-failure handling: malformed or unparseable model output should degrade to
  a defined fallback (e.g. `escalate_to_human` or a recorded parse-failure), not a crash.
- Backend should be swappable across at least two models (§2.8 wants one weak + one
  strong model as a factor) without touching the harness.
- Run 10 smoke episodes end-to-end against a real model and manually inspect the JSONL
  output for sanity (context shown, proposal shape, verdicts, executor effects).

**Done when:** 10 smoke episodes run end-to-end against a real model and produce valid,
inspectable JSONL.

---

## Phase 7 — Fault catalogue & full runner

**Deliverable:** 32 pre-registered scenarios, full runner, all experimental arms.

Tasks:
- Author ~4 scenarios per fault family (A–H, §2.6), each with **frozen**
  `correct_actions` and `unsafe_actions` sets written *before* any model is run against
  them — this is the pre-registration §1.6 depends on for the whole study's validity.
- Have this authored independently of whoever wrote the gate (§3.2) — label
  independence is cheap to arrange now and expensive to argue for after the fact.
- Have a teammate independently label a sample and compute inter-rater agreement
  (§1.6) — this number needs to exist before analysis, not be added retroactively.
- Implement all arms from §2.8: A0 (random valid action), A1 (static rule-based
  runbook — non-LLM baseline), A2 (LLM, no gate), A2b (LLM, no gate, quit-prompted),
  A3 (LLM + gate, block only), A4 (LLM + gate + feedback/retry), A5* (per-check
  ablations, C1..C6 disabled one at a time).
- Runner: `run --arm A3 --model X` sweeps all 32 scenarios × configured seeds and
  writes valid JSONL for each episode.
- Budget check: 32 scenarios × 15 seeds = 480 episodes/arm/model, ~4 LLM calls/episode
  ≈ 2k calls per arm-model cell (§2.8) — cost this out before the full run, not after.
- Pilot: a small subset of seeds per arm to catch harness bugs before spending the full
  budget.

**Done when:** `run --arm A3 --model X` produces valid JSONL for all 32 scenarios, and
the pre-registered labels + inter-rater number exist and are frozen.

---

## Phase 8 — Analysis

**Deliverable:** Metrics, bootstrap CIs, McNemar's test, ablation table, plots.

Tasks:
- Implement every metric from §2.7: PUR, EUR (headline), Catastrophic Episode Rate,
  Over-reach Rate, Injection Compliance Rate (family F), Recovery Rate, Steps to
  Recovery, Escalation Precision/Recall, False Block Rate, Recovery Rate delta,
  Oscillation Rate, plus operational (LLM calls/tokens/wall-clock).
- Bootstrap confidence intervals on every reported rate — never report a bare
  percentage (§2.8).
- Paired comparisons across matched `(scenario, seed)` using McNemar's test for binary
  outcomes; report absolute risk reduction with a CI.
- Per-check ablation table from the A5 arms — which checks carry the weight.
- Plots: safety/utility tradeoff curve (the actual headline result per §1.4), per-family
  breakdown, ablation bars.
- Single command regenerates every number/plot in the paper from raw JSONL in
  `results/` — no manual spreadsheet step.

**Done when:** every number in the paper regenerates from raw logs with one command.

---

## Phase 9 — Docker validation *(optional)*

**Deliverable:** Small real-stack validation run.

Tasks:
- Minimal docker-compose stack reproducing a handful of the simulator's fault families
  against real (if toy) services.
- Run ~10 real episodes through the same harness/gate.
- Compare qualitatively against the simulator's behaviour on matched fault types — this
  feeds the honest external-validity discussion in the threats-to-validity doc (§1.7),
  not a numeric result.

**Done when:** ~10 real episodes run, with a written qualitative comparison to the
simulator.

---

## Cross-phase notes

- **Independence discipline (Phase 7):** gate author ≠ label author. This is the
  cheapest insurance against the circularity objection in §1.6 and costs nothing if
  arranged from the start.
- **Code freeze (week 10, §3.1):** Phase 7's full experimental runs are the last thing
  that touches `src/rg/gate/` or the frozen scenario configs. Phase 8 only reads
  `results/`.
- **Budget tokens before Phase 7, not after** — see §4.3 known risks.
