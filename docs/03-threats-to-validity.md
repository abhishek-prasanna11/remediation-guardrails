# Threats to Validity

These are stated plainly, so that a reviewer doesn't have to find them. The paper's
threats section is written from this file.

## Internal validity

**Circular ground truth.** One author wrote the simulator, the catalogue, the labeller and
the gate. Three mitigations are in place:
- The catalogue and its labels were committed (`daf5f20`) before any gate code existed.
- Its sha256 is stamped into every episode record.
- Labelling is mechanical: patterns plus a counterfactual simulation, with no judgement
  calls after seeing results.

The labeller never imports the gate. The strongest mitigation is an independent rater's
Cohen's κ on a blinded, stratified sample of 80 distinct proposals, rated with
[`irr-rater-guide.md`](irr-rater-guide.md). The independent first pass
(`rater_unsafe` in `results/derived/irr_sheet.csv`) agrees on 89% of rows, κ = 0.78.
All 9 disagreements came from rule 3: the rater marked reversible changes to a caller of
the faulty service as unsafe, although the guide counts such callers as involved. On
every other kind of proposal the rater and the labeller agreed on every row. Asked about
the rule afterwards, the rater confirmed the misreading and changed 7 of the 9
(`rater_revised`: 97.5%, κ = 0.95). The two they kept (D3 rollback after the blip had
cleared; A1 change to frontend, an indirect caller) are ambiguous under the guide. The
paper reports both passes, with the first pass as the independent measure.

**The gate was adjusted during mock validation.** Two changes were made after the gate
first ran against the scripted mocks, and both happened before any LLM call:
- C1 was restricted to signal-compatible dependency anomalies.
- C1 gained the noisy-neighbour co-client rule.

The simulator's surge-mitigation test was also changed from a replica count to a load
threshold. All of this is in commit history (Phases 4–5). A third C1 false block
(corruption that doesn't show in the cache's own metrics) was deliberately left in place.

**Post hoc additions.** Two things were added after the main results, in response to an
internal review:
- Simpler-gate baselines: a deny-list of irreversible actions (`A3d`, `A1d`,
  `M-correct-deny`) and the policy table alone (`A3p`). They reuse the frozen labeller,
  seeds and response cache.
- Family I, four gate-aware injection scenarios in `configs/scenarios_adaptive.yaml`. They
  were written knowing the gate's rules (that is what makes them gate-aware), so they are
  kept out of the frozen catalogue, logged to `results/raw_adaptive/`, and reported
  separately, as counts. `tests/test_adaptive.py` checks that every injected action passes
  the full gate and that the frozen catalogue's hash is unchanged.

**The gate reads ground truth.** C1, C3 and C6 query simulator state, not a noisy
monitoring pipeline. A real gate reads monitoring data that may lag or be wrong, so our
gate numbers are an upper bound on what a deployed gate would achieve.

**The harness can't tell proposers apart.** The proposer interface is identical for
mocks, the runbook and LLMs, and only mocks receive the scenario. A test asserts that no
ground-truth fault name appears in the context the LLM sees.

## Construct validity

- "Unsafe" is the five-class definition in `00-problem-and-plan.md` §1.6, made
  operational in `02-fault-catalogue.md`. Harm uses a 3-tick counterfactual against
  `no_op`. A slower-acting harm would be missed.
- The health score weights are a modelling choice. Recovery and resolution don't depend
  on them; they use alert thresholds.
- **False blocks are measured against the declared correct set.** A sensible action that
  isn't in the set is labelled neutral, not correct, so blocking it doesn't count as a
  false block. The false-block rate is therefore a lower bound.
- Runbook notes in the context give general advice, such as "never delete data
  directories". That makes the prompt-only arms more conservative than they would be with
  no runbook. This favours the no-gate arms, so it doesn't inflate the gate's measured
  benefit.

## External validity

- **Simulator, not a cluster.** One fixed 10-service topology and 32 scenarios. The
  optional Docker validation (Phase 9) was **not run**.
- **Small local models.** Llama-3.2-3B and Qwen2.5-7B ran through Ollama with
  schema-constrained decoding at temperature 0.7. Frontier models may fail less often,
  and differently. The gate's value is model-agnostic, but its measured benefit is not.
- **Fixed step budget.** K = 6 decision steps, with one simulator tick of decision
  latency per proposal.

## Statistical conclusion validity

- **Sample size is limited by local inference speed.** Llama main arms ran 32 scenarios ×
  3 seeds and the Llama ablations 32 × 2; Qwen main arms ran 32 × 1. Non-LLM arms ran 32 × 15.
- Seeds of one scenario are correlated, so every CI is a **cluster bootstrap over
  scenarios** (2000 resamples). Because of this, the effective sample size is 32
  clusters, not the episode count.
- Arm comparisons are paired on (scenario, seed). The test is an exact two-sided **sign
  test over scenarios** (each scenario counts once, by the sign of its seed-averaged
  difference). McNemar over episodes is kept in `summary.md` for reference only: it
  treats correlated seeds as independent and, for the runbook, reports p < 1e-4 for an
  effect carried by one scenario.
- A sign test over k scenarios cannot go below 2^(1-k) (0.0625 for five scenarios), so
  effects confined to a few scenarios cannot reach significance however many seeds run.
- When no episode has the event, the bootstrap interval collapses to [0, 0]. The upper
  limit is then the exact Clopper-Pearson bound with scenarios as units (10.9% for 32).
- 32 paired comparisons are reported without multiple-comparison correction. Under
  Bonferroni the Llama safety result (p = 0.00024) survives; the Qwen feedback gain
  (p = 0.016) and the runbook gain (p = 0.062) do not.
