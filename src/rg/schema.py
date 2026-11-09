"""JSONL log schema. One line per episode; each line nests its steps.

This schema is load-bearing: Phase 8 analysis reads nothing but these records.
Documented field by field in docs/schema.md. Bump SCHEMA_VERSION on any change.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from rg.actions.catalogue import Proposal

SCHEMA_VERSION = 1

Outcome = Literal["recovered", "escalated", "catastrophic", "budget_exhausted"]
UnsafeClass = Literal[
    "wrong_target",
    "destructive_overreach",
    "invariant_violation",
    "harmful_effect",
    "injection_compliance",
]


class CheckResult(BaseModel):
    check: str  # C1..C6
    passed: bool
    enabled: bool  # disabled checks still run in shadow mode and are logged
    reason: str = ""


class Verdict(BaseModel):
    decision: Literal["approve", "block"]
    checks: list[CheckResult]
    reason: str = ""  # structured reason of the first enabled failing check

    @property
    def failed(self) -> list[str]:
        return [c.check for c in self.checks if c.enabled and not c.passed]

    @property
    def shadow_failed(self) -> list[str]:
        return [c.check for c in self.checks if not c.passed]


class Label(BaseModel):
    """Mechanical, pre-registered grading of one proposal (docs/02-fault-catalogue.md)."""

    unsafe: bool
    classes: list[UnsafeClass] = Field(default_factory=list)
    correct: bool = False
    unnecessary: bool = False  # mutating action in a scenario whose correct answer is no_op
    matched_rule: str = ""


class LLMMeta(BaseModel):
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    cache_hits: int = 0
    parse_failures: int = 0


class StepRecord(BaseModel):
    step: int
    attempt: int  # >0 only for feedback-retry arms (A4)
    tick: int
    context_sha: str
    proposal: Proposal | None
    parse_error: str | None = None
    label: Label
    verdict: Verdict | None  # None when the arm has no gate
    executed: bool
    health_before: float
    health_after: float
    damage: list[str] = Field(default_factory=list)
    llm: LLMMeta = Field(default_factory=LLMMeta)


class EpisodeRecord(BaseModel):
    schema_version: int = SCHEMA_VERSION
    episode_id: str
    arm: str
    model: str
    scenario_id: str
    family: str
    expected: str
    seed: int
    catalogue_sha: str  # sha256 of the frozen scenario catalogue the labels came from
    outcome: Outcome
    resolved: bool  # outcome matches the scenario's pre-registered expectation
    steps_used: int
    final_health: float
    damage: list[str] = Field(default_factory=list)
    trace_sha: str
    wallclock_s: float
    steps: list[StepRecord]
