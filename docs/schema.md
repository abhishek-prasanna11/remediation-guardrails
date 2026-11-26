# Episode log schema (v1)

Defined in [`src/rg/schema.py`](../src/rg/schema.py). Every run writes one JSONL file per
`(arm, model)` cell under `results/raw/`. **Each line is one episode**; the episode nests its
steps. Phase 8 analysis reads nothing but these records.

## EpisodeRecord

| Field | Meaning |
|---|---|
| `schema_version` | Bumped on any change to this schema |
| `episode_id` | `{arm}/{model}/{scenario_id}/{seed}` |
| `arm`, `model` | Experimental cell (configs/arms.yaml, configs/models.yaml) |
| `scenario_id`, `family`, `expected` | From the frozen catalogue (configs/scenarios.yaml) |
| `seed` | Seeds the simulator noise, the log generator and the model's sampler |
| `catalogue_sha` | sha256 of `configs/scenarios.yaml` at run time. Proves labels were frozen |
| `outcome` | `recovered` · `escalated` · `catastrophic` · `budget_exhausted` |
| `resolved` | Outcome matches the scenario's pre-registered expectation (see catalogue doc) |
| `steps_used` | Decision steps taken (each step can include retries in A4) |
| `final_health` | Ground-truth health score in [0, 1] at episode end |
| `damage` | Every damage event the simulator recorded (data loss, invariant breach, ...) |
| `trace_sha` | sha256 of the full ground-truth state trace (determinism check) |
| `wallclock_s` | Wall-clock time for the episode |
| `steps` | List of StepRecord |

## StepRecord

| Field | Meaning |
|---|---|
| `step`, `attempt` | Step index (1-based) and retry index within the step (A4 only) |
| `tick` | Simulator tick at which the context was built |
| `context_sha` | sha256 of the exact text shown to the proposer |
| `proposal` | Typed `Proposal` (action, target, n, path, evidence, reason) or null on parse failure |
| `parse_error` | Why the model output could not be parsed, if it could not |
| `label` | Pre-registered mechanical grading: `unsafe`, `classes`, `correct`, `unnecessary`, `matched_rule` |
| `verdict` | Gate verdict: `decision` plus all six `checks`, each with `enabled` and `passed`. Disabled checks still run in **shadow mode**, so every log says what each check would have done. The deny-list baseline gate (arms `A3d`, `A1d`, `M-correct-deny`) adds a seventh entry, `DL`, which is its only enabled check |
| `executed` | Whether the proposal reached the executor |
| `health_before`, `health_after` | Ground-truth health around execution |
| `damage` | Damage events caused during this step |
| `llm` | Calls, prompt/completion tokens, latency, cache hits, parse failures |
