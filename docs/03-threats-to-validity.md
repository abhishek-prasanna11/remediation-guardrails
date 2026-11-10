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

The labeller never imports the gate. The strongest mitigation, an independent rater's
Cohen's κ on a blinded sample, is tooled (`rg irr`) but **has not been run**. It must
exist before submission.

**The gate was adjusted during mock validation.** Two changes were made after the gate
first ran against the scripted mocks, and both happened before any LLM call:
- C1 was restricted to signal-compatible dependency anomalies.
- C1 gained the noisy-neighbour co-client rule.

The simulator's surge-mitigation test was also changed from a replica count to a load
threshold. All of this is in commit history (Phases 4–5). A third C1 false block
(corruption that doesn't show in the cache's own metrics) was deliberately left in place.

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

- **Sample size is limited by local inference speed.** Each Llama arm (main and ablation)
  ran 32 scenarios × 2 seeds; Qwen main arms run 32 × 1. Non-LLM arms ran 32 × 15.
- Seeds of one scenario are correlated, so every CI is a **cluster bootstrap over
  scenarios** (2000 resamples). Because of this, the effective sample size is 32
  clusters, not the episode count.
- Arm comparisons are paired on (scenario, seed) with exact McNemar tests. Several
  comparisons are reported, and no multiple-comparison correction is applied. Read
  p-values near 0.05 with that in mind.
