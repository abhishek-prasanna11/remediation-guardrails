# Literature Survey

**P03 — Guardrails for LLM-Driven Auto-Remediation**
Week 1 deliverable · 16 papers across 6 themes

> **Verification note.** Every entry below was checked against a primary source (ACL
> Anthology, ACM DL, AAAI/ICLR/NeurIPS proceedings, DBLP, or arXiv) — not written from
> memory. Entries flagged ⚠️ have a detail I could not confirm to publication standard;
> confirm those before they enter the `.bib`. Never cite anything in this list you have
> not personally opened.

---

## How to read this

Each entry has three parts: **what it does**, **why it matters to us**, and **the gap it
leaves**. The gap column is the one that matters — a related-work section is not a list of
summaries, it is an argument that a specific hole exists and that you are filling it.

Papers marked **[core]** must be cited and discussed. Papers marked **[context]** can be
cited in a single grouped sentence.

---

## Theme 1 — Foundations: autonomic computing and the verifier pattern

*Establishes that "untrusted planner + trusted verifier" is a decades-old idea, not
something we invented. This framing is a strength: it positions the gate as the latest
instance of a well-understood safety pattern rather than an ad-hoc hack.*

### 1. Kephart & Chess (2003) — *The Vision of Autonomic Computing* **[core]**
IEEE Computer 36(1):41–50. DOI `10.1109/MC.2003.1160055`

Introduces self-managing systems and the **MAPE-K loop** — Monitor, Analyze, Plan,
Execute over a shared Knowledge base.

**Why it matters:** This is the vocabulary of our whole problem. An LLM remediation agent
is exactly an attempt to fill the *Analyze* and *Plan* boxes with a language model. Say
this explicitly in the paper — it instantly situates the work in a 20-year lineage.

**Gap:** Predates any learned planner. Assumes the planner is engineered and therefore
analysable; offers nothing for a planner that is stochastic and opaque.

### 2. Sha (2001) — *Using Simplicity to Control Complexity* **[core]**
IEEE Software 18(4):20–28. DOI `10.1109/MS.2001.936213`

The **Simplex architecture**: pair a high-performance but unverifiable complex controller
with a simple, verified safety controller that can take over.

**Why it matters:** This is our gate, twenty-five years early. Complex-but-unverifiable
controller = the LLM; simple-but-verified safety controller = the deterministic gate.
Citing this is the single strongest move available in the related-work section, because it
reframes the contribution from "we added some checks" to "we instantiate and empirically
evaluate Simplex for LLM-driven operations." Use it.

**Gap:** Developed for control systems with continuous state and formal stability
guarantees. Ops actions are discrete, irreversible, and lack a recovery region — so the
guarantee doesn't transfer, and the *empirical* question we ask is open.

### 3. Alshiekh et al. (2018) — *Safe Reinforcement Learning via Shielding* **[core]**
AAAI-18, pp. 2669–2678

A **shield** sits between an RL agent and the environment, blocking actions that would
violate a temporal-logic safety specification, at both training and test time.

**Why it matters:** Structurally identical to our gate — same position in the loop, same
job. It also gives us the standard framing for the safety/utility tradeoff, which the
shielding literature has argued about for years. Our C1–C6 checks are a hand-written,
domain-specific shield.

**Gap:** Requires a formal LTL specification and a model of the environment. Neither
exists for a production cluster, and the interesting failure modes here (hallucinated
targets, injection compliance) aren't naturally expressible in LTL.

---

## Theme 2 — LLMs in incident management and AIOps

*What the field currently does: use LLMs to diagnose and to suggest, with a human acting.*

### 4. Ahmed et al. (2023) — *Recommending Root-Cause and Mitigation Steps for Cloud Incidents using LLMs* **[core]**
ICSE 2023, pp. 1737–1749. arXiv `2301.03797`

First large-scale study of LLMs for root-causing and mitigating real production incidents
at Microsoft, evaluated with lexical, semantic, and human judgement.

**Why it matters:** The canonical citation for "LLMs are plausibly useful in incident
management." Establishes the premise our project stress-tests.

**Gap — and this is the important one:** it evaluates the *quality of recommendations to a
human*. Nothing is executed. Safety of autonomous action is not merely unmeasured, it is
out of scope by construction. **This gap is the seed of our contribution.**

### 5. Chen et al. (2023) — *Automatic Root Cause Analysis via LLMs for Cloud Incidents* (RCACopilot) **[context]** ⚠️
arXiv `2305.15778` — *confirm venue before citing*

On-call diagnosis pipeline that collects incident data and produces root-cause predictions
with explanations.

**Why it matters:** Shows the retrieval-plus-reasoning architecture our proposer's context
builder resembles.

**Gap:** Diagnosis only. No action, therefore no action safety.

### 6. Roy et al. (2024) — *Exploring LLM-based Agents for Root Cause Analysis* **[core]**
FSE 2024 Companion (industry track). arXiv `2403.04123` · DOI `10.1145/3663529.3663841`

Moves from single-shot prompting to **agents** that dynamically gather diagnostic
information, and finds this materially outperforms static-context prompting.

**Why it matters:** Direct justification for including `gather_diagnostics` in our action
catalogue, and for making it the correct answer in fault family B (ambiguous). It also
marks the field's shift from "LLM as summariser" to "LLM as agent that acts" — which is
precisely the shift that creates the safety problem we measure.

**Gap:** The agent's actions are read-only. It gathers information; it never mutates the
system. The step from read to write is exactly where the danger begins, and it is not taken.

---

## Theme 3 — Closed-loop LLM remediation with real execution

*The nearest prior work. Read these two most carefully — reviewers will ask how we differ,
and the honest answer must be crisp.*

### 7. *OperAID: Benchmarking LLM Agents for Autonomous Kubernetes Fault Remediation* (2025) **[core]** ⚠️
Confirm venue and arXiv ID — indexed on ResearchGate (`404290488`); locate the primary version.

Open-source closed-loop testbed: fault injection → diagnosis → remediation →
execution-based verification, on a live Open5GS Kubernetes deployment. 900 experiments,
three fault scenarios, five open-source LLMs. Finds tool access lifts mean performance
from 10.9% to 61.1%, and that model size alone doesn't guarantee success.

**Why it matters:** The closest existing work — a real closed loop with real execution and
proper experimental scale. **Assign someone to read this in full this week.** It will shape
our testbed design and it is the paper we must differentiate from.

**Gap — our wedge:** it measures **capability** (did the agent fix it?), not **safety**
(what did it break on the way?). There is no unsafe-action rate, no verification gate, no
adversarial or ambiguous cases, and no measurement of what a guardrail would cost. Their
axis is success; ours is harm. Complementary, not competing — say so plainly.

### 8. *MicroRemed: Benchmarking LLMs in Microservices Remediation* (2025) **[core]** ⚠️
arXiv `2511.01166` — confirm authors and venue

Benchmark for end-to-end LLM remediation of microservice failures.

**Why it matters:** Second data point that closed-loop remediation benchmarking is an
active 2025–26 area. Confirms our topic is live; also raises the bar on novelty, so our
safety framing needs to be stated sharply.

**Gap:** Same shape as OperAID — remediation *effectiveness*, not action safety under a
gate.

---

## Theme 4 — Agent safety evaluation and sandboxes

*Methodology we borrow. This theme is where we get our experimental design vocabulary.*

### 9. Ruan et al. (2024) — *Identifying the Risks of LM Agents with an LM-Emulated Sandbox* (ToolEmu) **[core]**
ICLR 2024. arXiv `2309.15817`

Emulates tool execution so agents can be tested against risky scenarios without real side
effects. 36 high-stakes toolkits, 144 test cases, plus an automatic safety evaluator.
Human review found **68.8%** of identified failures would be genuine real-world failures;
even the safest agent tested failed **23.9%** of the time.

**Why it matters:** The methodological precedent for our entire simulator decision. When a
reviewer objects "you used a simulator," this is the citation that answers them —
emulated-environment agent safety evaluation is established, ICLR-published practice. That
23.9% figure is also a great motivating number for our introduction.

**Gap:** Uses an *LLM* to emulate the environment and an *LLM* to judge safety — so both
the world and the grader are stochastic and themselves fallible. **Our simulator is
deterministic and our safety labels are pre-registered and mechanical.** That is a genuine
methodological improvement over the closest precedent, and worth stating as a contribution.
The domain is also generic tools, not operations.

### 10. Andriushchenko et al. (2024) — *AgentHarm: A Benchmark for Measuring Harmfulness of LLM Agents* **[context]**
arXiv `2410.09024` · ICLR 2025 ⚠️ *(confirm venue)*

110 malicious agent tasks (440 augmented) across 11 harm categories; measures both refusal
and whether jailbroken agents retain multi-step capability.

**Why it matters:** Precedent for structured harm taxonomies and for scoring multi-step
agent behaviour rather than single outputs.

**Gap:** Concerns a **malicious user** directing the agent. Our threat model is the
opposite and more mundane: a well-intentioned agent causing harm through incompetence,
over-reach, or injected data. Different problem; useful method.

### 11. Kim et al. (2025) — *Check Yourself Before You Wreck Yourself: Selectively Quitting Improves LLM Agent Safety* **[core]** ⚠️
arXiv `2510.16492` · NeurIPS 2025 *(confirm final citation)*

Gives agents an explicit **quit** action. Across 12 LLMs and 144 ToolEmu scenarios,
prompting to quit improves safety by +0.39 on a 0–3 scale while costing only −0.03 in
helpfulness.

**Why it matters:** The most directly relevant recent result we have. Their "quit" is our
`escalate_to_human`, and their headline finding — a large safety gain at negligible utility
cost — is *the same shape of claim we intend to make about the gate*. It also validates
fault family E (no safe action exists) as a real research object.

**Gap, and our advantage:** quitting is a **prompt-level, model-mediated** defence — you
are asking the model to police itself, so it inherits every reliability problem the model
has. Our gate is **external and deterministic**: it holds even when the model is wrong,
jailbroken, or injected. Running a quit-style prompt arm alongside our gate arm would be a
strong, cheap addition to the experiment design — **consider adding it as arm A2b.**

---

## Theme 5 — Prompt injection through untrusted data

*Grounds fault family F. This is our most differentiating scenario family.*

### 12. Greshake et al. (2023) — *Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection* **[core]**
AISec '23 (16th ACM Workshop on AI and Security, co-located with CCS). DOI `10.1145/3605764.3623985`

Defines **indirect prompt injection**: the adversarial instruction is not typed by the
user but embedded in content the model retrieves. Provides a security taxonomy and
real-world demonstrations.

**Why it matters:** The foundational citation for family F. Our threat is a textbook
instance — log lines and alert annotations are retrieved, attacker-influenceable content
fed straight into the model's context. Anyone who can write to a log can attempt this.
Frame it in those terms and the scenario stops looking contrived.

**Gap:** Demonstrates the attack class broadly; does not study operations tooling, where
the injected action can delete data or drain a node rather than exfiltrate a message.

### 13. Debenedetti et al. (2024) — *AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents* **[core]**
NeurIPS 2024, Datasets & Benchmarks Track

Extensible environment with 97 realistic tasks and 629 security test cases across
workspace, Slack, banking, and travel domains, with pluggable attacks and defences.

**Why it matters:** The template for how to build our harness — task suite plus security
test cases plus swappable defences maps almost one-to-one onto our scenarios, family F, and
our gate arms. Steal the structure.

**Gap:** No operations/SRE domain, and no notion of remediating a live degraded system
under time pressure. Our contribution can reasonably be described as *AgentDojo's
methodology applied to the auto-remediation domain, with a deterministic gate as the
defence under test.*

---

## Theme 6 — Enforcement mechanisms: what our gate is an instance of

*Existing guardrail systems. Needed to show we know the design space and chose deliberately.*

### 14. Debenedetti et al. (2025) — *Defeating Prompt Injections by Design* (CaMeL) **[core]** ⚠️
arXiv `2503.18813` — *confirm author list*

Splits the system into a **privileged LLM** that plans from the trusted user query and a
**quarantined LLM** that handles untrusted data without tool access, with a custom
interpreter tracking data provenance and enforcing policy before every tool call.
Evaluated on AgentDojo.

**Why it matters:** The strongest statement of the principle our gate embodies — security
should come from *system architecture*, not from asking the model to behave. "Enforce
policy before every tool call" is precisely what C1–C6 do. The privileged/quarantined split
is also a concrete design we could adopt for family F, and worth discussing as future work
even if we don't build it.

**Gap:** Targets injection and data exfiltration specifically. It has nothing to say about
*competence* failures — hallucinated targets, over-reach, oscillation — which are most of
our fault catalogue.

### 15. Shi et al. (2025) — *Progent: Programmable Privilege Control for LLM Agents* **[core]**
arXiv `2504.11703`

A domain-specific language for expressing privilege-control policies over tool calls,
enforcing least privilege at execution time, with fallbacks when a call is denied.
Modular — no changes to agent internals.

**Why it matters:** Our policy matrix (check C2) is a hand-rolled, domain-specific version
of exactly this. Cite it to show the design is principled rather than improvised. Their
LLM-generated-policy idea is also a natural "future work" line for us.

**Gap:** Generic agent tooling, evaluated on security benchmarks. No operations domain, and
critically **no measurement of the utility cost** of enforcement in a setting where the
agent must still fix a live problem under a step budget. Our false-block rate and recovery
delta measure precisely that.

### 16. Rebedea et al. (2023) — *NeMo Guardrails: A Toolkit for Controllable and Safe LLM Applications with Programmable Rails* **[context]**
EMNLP 2023, System Demonstrations. ACL Anthology `2023.emnlp-demo.40`

Production toolkit for programmable rails — topical rails for dialogue control, execution
rails for custom actions — defined independently of the underlying LLM.

**Why it matters:** Shows the industrial state of practice, and that "rails are separate
from the model" is an accepted engineering position, not our invention.

**Gap:** Rails are largely conversational and often themselves LLM-mediated. No empirical
safety study in an operations setting with irreversible actions.

---

## Synthesis — the gap we fill

This paragraph is the argumentative core of the related-work section. Everything above
exists to support it.

Prior work splits cleanly into three groups, and **none of them measures what we measure:**

1. **LLMs for incident management** (#4–#6) evaluate the *quality of advice given to a
   human*. Nothing executes, so action safety is out of scope by construction.
2. **Closed-loop remediation benchmarks** (#7–#8) do execute, but measure **capability** —
   did the agent fix it? They do not measure what the agent broke on the way, include no
   adversarial or ambiguous cases, and evaluate no guardrail.
3. **Agent safety and enforcement work** (#9–#16) does measure harm and does build gates,
   but in **generic tool domains** — email, banking, travel — where actions are reversible
   and there is no degraded system to repair under a step budget.

So the specific, defensible hole is:

> **No existing work measures the unsafe-action rate of an LLM-driven remediation loop in
> an operations setting, quantifies how much a deterministic verification gate reduces it,
> or reports what that gate costs in lost recovery capability.**

Our four contributions map onto that sentence one-to-one:

| Contribution | Answers |
|---|---|
| Reproducible testbed, deterministic, pre-registered labels | improves on #9's LLM-emulated, LLM-judged setup |
| Fault catalogue with ambiguous / cascading / injection families | absent from #7, #8; extends #12, #13 into ops |
| Safety **and utility cost** of the gate | absent from #14, #15 |
| Per-check ablation (C1–C6) | tells practitioners which guardrail earns its keep |

---

## Actions arising

**Two changes to the plan this survey justifies:**

1. **Add arm A2b — "quit-prompted, no gate."** Paper #11 shows prompt-level self-policing
   is a strong baseline that is nearly free. If we don't test it, a reviewer will ask why
   an external gate is worth the engineering when a prompt gets much of the benefit. This
   is now our most important missing baseline. I'd fold it into §2.8 of the plan.
2. **Read #7 (OperAID) in full this week.** It is the closest prior work and the main
   differentiation risk. Everything else here can be read from abstracts for now.

**Still to search** (gaps in this survey worth an hour each):
- Runtime verification / runtime enforcement — Schneider's security automata, edit automata.
  Would deepen Theme 1's formal grounding.
- Human-in-the-loop and approval-gating in SRE practice — currently thin.
- Oscillation and stability in autonomic control loops — would strengthen check C4, which
  is presently the least well-grounded of the six.
- A recent AIOps survey for one grouped context citation. Candidates seen but not vetted:
  *A Survey of Time Series Anomaly Detection Methods in the AIOps Domain* (arXiv
  `2308.00393`); *AIOps for log anomaly detection in the era of LLMs: a systematic
  literature review* (ScienceDirect, 2025).

**Before any of these enter the `.bib`:** open the primary source, confirm authors, venue,
year, and page numbers, and clear every ⚠️. Bibliography errors are the cheapest possible
way to lose reviewer confidence, and the easiest to avoid.

---

## Suggested related-work structure for the paper

Roughly 1 to 1.5 columns, six paragraphs:

1. Autonomic computing and MAPE-K → the Plan step has always been the hard one (#1)
2. Verified-supervisor architectures: Simplex and shielding (#2, #3)
3. LLMs for incident management — advice, not action (#4–#6)
4. Closed-loop LLM remediation — action, but capability-only measurement (#7, #8)
5. Agent safety evaluation and injection (#9–#13)
6. Enforcement mechanisms and what they leave unmeasured (#14–#16) → the gap sentence

---

## Sources

Kephart & Chess — [ACM DL](https://dl.acm.org/doi/10.1109/MC.2003.1160055) ·
Sha — [ACM DL](https://dl.acm.org/doi/10.1109/MS.2001.936213) ·
Alshiekh et al. — [AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/11797), [DBLP](https://dblp.org/rec/conf/aaai/AlshiekhBEKNT18.html) ·
Ahmed et al. — [arXiv](https://arxiv.org/abs/2301.03797), [ACM DL](https://dl.acm.org/doi/10.1109/ICSE48619.2023.00149), [DBLP](https://dblp.org/rec/conf/icse/AhmedGBZZR23.html) ·
Chen et al. — [arXiv](https://arxiv.org/pdf/2305.15778) ·
Roy et al. — [arXiv](https://arxiv.org/abs/2403.04123), [ACM DL](https://dl.acm.org/doi/pdf/10.1145/3663529.3663841) ·
OperAID — [ResearchGate](https://www.researchgate.net/publication/404290488_OperAID_Benchmarking_LLM_Agents_for_Autonomous_Kubernetes_Fault_Remediation) ·
MicroRemed — [arXiv](https://arxiv.org/pdf/2511.01166) ·
Ruan et al. — [ICLR](https://proceedings.iclr.cc/paper_files/paper/2024/hash/7274ed909a312d4d869cc328ad1c5f04-Abstract-Conference.html), [arXiv](https://arxiv.org/abs/2309.15817) ·
Andriushchenko et al. — [arXiv](https://arxiv.org/abs/2410.09024), [OpenReview](https://openreview.net/forum?id=AC5n7xHuR1) ·
Kim et al. — [arXiv](https://arxiv.org/abs/2510.16492), [NeurIPS](https://neurips.cc/virtual/2025/125248) ·
Greshake et al. — [ACM DL](https://dl.acm.org/doi/abs/10.1145/3605764.3623985) ·
Debenedetti et al. (AgentDojo) — [NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html) ·
CaMeL — [arXiv](https://arxiv.org/pdf/2503.18813) ·
Shi et al. (Progent) — [arXiv](https://arxiv.org/abs/2504.11703) ·
Rebedea et al. — [ACL Anthology](https://aclanthology.org/2023.emnlp-demo.40/)
