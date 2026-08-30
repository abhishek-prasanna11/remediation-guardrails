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
| 0 | Repo skeleton, config, log schema, CI | not started |
| 1 | Simulator core | not started |
| 2 | Observer, alerts, context builder | not started |
| 3 | Action catalogue + executor | not started |
| 4 | Mock proposers | not started |
| 5 | **Verification gate** | not started |
| 6 | LLM proposer | not started |
| 7 | Fault catalogue + full runner | not started |
| 8 | Analysis + stats | not started |
| 9 | Docker validation *(optional)* | not started |

Phases 4–5 come before 6 deliberately: the gate is built and fully tested against scripted
mock proposers at zero API cost, so that when a real model is plugged in, everything
downstream is already trusted.

## Team

| Sub-role | Responsibility |
|---|---|
| Testbed & Implementation | Fault testbed, LLM integration, verification gate (Phases 0–6) |
| Measurement & Analysis | Fault catalogue, unsafe-action and recovery measurement (Phases 7–8) |
| Related Work & Writing | Related work on autonomic/LLM ops, write-up (from week 1) |

Fault-catalogue labelling is kept **independent** of gate implementation — labels are
pre-registered and frozen before any model runs, so the safety grading isn't tuned to the
implementation being graded.
