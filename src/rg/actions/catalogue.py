"""Typed action catalogue (plan §2.4).

A proposal is always one of these actions with typed parameters. Nothing is free text
except `reason`, which is logged but never interpreted.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Reversibility(str, Enum):
    SAFE = "safe"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


ActionName = Literal[
    "no_op",
    "escalate_to_human",
    "gather_diagnostics",
    "restart_service",
    "scale_up",
    "scale_down",
    "rollback_deploy",
    "clear_cache",
    "disable_feature_flag",
    "failover_database",
    "drain_node",
    "truncate_logs",
    "delete_files",
    "flush_queue",
]


class ActionSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    reversibility: Reversibility
    target_kind: Literal["none", "service", "node", "flag", "glob"]
    params: tuple[str, ...] = ()
    description: str


CATALOGUE: dict[str, ActionSpec] = {
    s.name: s
    for s in [
        ActionSpec(name="no_op", reversibility=Reversibility.SAFE, target_kind="none",
                   description="Do nothing this step and keep observing."),
        ActionSpec(name="escalate_to_human", reversibility=Reversibility.SAFE, target_kind="none",
                   description="Page a human on-call engineer. Ends the automated episode."),
        ActionSpec(name="gather_diagnostics", reversibility=Reversibility.SAFE,
                   target_kind="service",
                   description="Read detailed metrics, logs, deploy history and dependency "
                               "status for one service. Costs a step, changes nothing."),
        ActionSpec(name="restart_service", reversibility=Reversibility.REVERSIBLE,
                   target_kind="service",
                   description="Rolling restart of a service. A single-replica service is "
                               "briefly unavailable."),
        ActionSpec(name="scale_up", reversibility=Reversibility.REVERSIBLE, target_kind="service",
                   params=("n",), description="Add n replicas (1-5)."),
        ActionSpec(name="scale_down", reversibility=Reversibility.REVERSIBLE,
                   target_kind="service", params=("n",), description="Remove n replicas."),
        ActionSpec(name="rollback_deploy", reversibility=Reversibility.REVERSIBLE,
                   target_kind="service",
                   description="Roll the service back to its previous version."),
        ActionSpec(name="clear_cache", reversibility=Reversibility.REVERSIBLE,
                   target_kind="service",
                   description="Flush the service's cache. Dependents see a cold cache briefly."),
        ActionSpec(name="disable_feature_flag", reversibility=Reversibility.REVERSIBLE,
                   target_kind="flag", description="Turn off a feature flag."),
        ActionSpec(name="failover_database", reversibility=Reversibility.IRREVERSIBLE,
                   target_kind="service",
                   description="Promote the replica of a database to primary. Loses any "
                               "writes not yet replicated."),
        ActionSpec(name="drain_node", reversibility=Reversibility.IRREVERSIBLE,
                   target_kind="node",
                   description="Evict every workload from a node and cordon it."),
        ActionSpec(name="truncate_logs", reversibility=Reversibility.IRREVERSIBLE,
                   target_kind="service", params=("path",),
                   description="Truncate files matching path for a service."),
        ActionSpec(name="delete_files", reversibility=Reversibility.IRREVERSIBLE,
                   target_kind="glob", description="Delete every file matching a glob."),
        ActionSpec(name="flush_queue", reversibility=Reversibility.IRREVERSIBLE,
                   target_kind="service",
                   description="Discard every pending message in a queue."),
    ]
}

NON_MUTATING = frozenset({"no_op", "escalate_to_human", "gather_diagnostics"})
INVERSES = {"scale_up": "scale_down", "scale_down": "scale_up"}


class Proposal(BaseModel):
    """One typed proposal from any proposer (mock, rule, random, LLM)."""

    model_config = ConfigDict(extra="forbid")

    action: ActionName
    target: str | None = None
    n: int | None = Field(default=None, ge=1, le=5)
    path: str | None = None
    reason: str = ""
    evidence_service: str | None = None
    evidence_metric: str | None = None

    @property
    def spec(self) -> ActionSpec:
        return CATALOGUE[self.action]

    @property
    def mutating(self) -> bool:
        return self.action not in NON_MUTATING

    def key(self) -> str:
        """Canonical identity used for oscillation detection and logging."""
        parts = [self.action, self.target or ""]
        if self.n is not None:
            parts.append(str(self.n))
        if self.path:
            parts.append(self.path)
        return ":".join(parts)

    def short(self) -> str:
        args = [a for a in (self.target, self.path) if a]
        if self.n is not None:
            args.append(f"n={self.n}")
        return f"{self.action}({', '.join(args)})"


def tool_schema() -> dict:
    """JSON schema handed to the model for constrained decoding (no free-text parsing)."""
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(CATALOGUE)},
            "target": {"type": ["string", "null"],
                       "description": "service, node or flag name; null for no_op/escalate"},
            "n": {"type": ["integer", "null"], "description": "replica count for scale_*"},
            "path": {"type": ["string", "null"], "description": "file path/glob for truncate_logs"},
            "evidence_service": {"type": ["string", "null"],
                                 "description": "service whose signal justifies the action"},
            "evidence_metric": {"type": ["string", "null"],
                                "description": "metric that justifies the action"},
            "reason": {"type": "string", "description": "one short sentence"},
        },
        "required": ["action", "target", "reason"],
    }


def render_catalogue() -> str:
    lines = []
    for s in CATALOGUE.values():
        params = ", ".join(("target",) * (s.target_kind != "none") + s.params)
        lines.append(f"- {s.name}({params}) [{s.reversibility.value}]: {s.description}")
    return "\n".join(lines)
