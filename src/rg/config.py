"""Config loading. Every config file is validated by pydantic at load time."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs"


# ---------------------------------------------------------------- topology
class ServiceConfig(BaseModel):
    name: str
    role: Literal["web", "app", "db_primary", "queue", "worker", "cache"] = "app"
    replicas: int = 2
    min_replicas: int = 1
    nodes: list[str]
    depends_on: list[str] = Field(default_factory=list)
    fanout: dict[str, float] = Field(default_factory=dict)  # calls per request
    base_cpu: float = 30.0
    base_mem: float = 40.0
    base_latency: float = 80.0
    base_error: float = 0.004
    base_disk: float = 40.0
    version: str = "v1.4.0"
    prev_version: str = "v1.3.9"
    flags: list[str] = Field(default_factory=list)
    log_dir: str = ""
    data_dir: str = ""


class Topology(BaseModel):
    nodes: list[str]
    services: list[ServiceConfig]

    @model_validator(mode="after")
    def _check(self) -> Topology:
        names = {s.name for s in self.services}
        for s in self.services:
            for d in s.depends_on:
                if d not in names:
                    raise ValueError(f"{s.name} depends on unknown service {d}")
            for n in s.nodes:
                if n not in self.nodes:
                    raise ValueError(f"{s.name} placed on unknown node {n}")
        return self


# ---------------------------------------------------------------- gate
class GateConfig(BaseModel):
    oscillation_window: int = 3  # W
    action_budget: int = 3  # M mutating actions per incident
    max_services_touched: int = 2  # N
    allowed_log_prefix: str = "/var/log/{service}/"
    max_failover_lag_s: float = 5.0
    always_permitted: list[str]
    policy: dict[str, list[str]]  # alert class -> permitted mutating actions


# ---------------------------------------------------------------- arms / models
class ArmConfig(BaseModel):
    name: str
    description: str
    proposer: Literal["random", "runbook", "llm", "mock"]
    mock: str | None = None
    gate: bool = False
    disabled_checks: list[str] = Field(default_factory=list)
    feedback: bool = False
    max_retries: int = 0
    prompt: Literal["base", "quit"] = "base"


class ModelConfig(BaseModel):
    name: str
    backend: Literal["ollama", "none"] = "ollama"
    model: str = ""
    temperature: float = 0.7
    num_ctx: int = 4096
    max_tokens: int = 200


# ---------------------------------------------------------------- scenarios
class ActionPattern(BaseModel):
    """Matches a proposal. `target`/`path_prefix` of None match anything."""

    action: str
    target: str | None = None
    path_prefix: str | None = None
    unsafe_class: str | None = None  # only meaningful inside unsafe_actions
    requires_diagnostics_on: str | None = None  # correct only after diagnosing this service


class FaultSpec(BaseModel):
    kind: str
    service: str | None = None
    flag: str | None = None
    rate: float = 1.0
    affects: str | None = None  # victim service for noisy_neighbor
    start_tick: int = 0
    duration: int | None = None  # transient faults self-resolve (family D)


class DecoySpec(BaseModel):
    service: str
    metric: str
    value: float
    log: str | None = None


class InjectionSpec(BaseModel):
    service: str
    where: Literal["log", "annotation"]
    text: str


class Scenario(BaseModel):
    id: str
    family: Literal["A", "B", "C", "D", "E", "F", "G", "H"]
    title: str
    expected: Literal["fix", "diagnose_then_fix", "no_op", "escalate"]
    faults: list[FaultSpec]
    decoys: list[DecoySpec] = Field(default_factory=list)
    injections: list[InjectionSpec] = Field(default_factory=list)
    implicated: list[str]  # ground-truth entities the incident legitimately involves
    correct_actions: list[ActionPattern]
    unsafe_actions: list[ActionPattern] = Field(default_factory=list)
    injected_actions: list[ActionPattern] = Field(default_factory=list)
    replica_lag_s: float = 0.5
    page_delay: int = 1  # ticks between the alert firing and the first decision
    notes: str = ""


def _load(path: Path) -> dict | list:
    return yaml.safe_load(path.read_text())


def load_topology(path: Path | None = None) -> Topology:
    return Topology.model_validate(_load(path or CONFIGS / "topology.yaml"))


def load_gate(path: Path | None = None) -> GateConfig:
    return GateConfig.model_validate(_load(path or CONFIGS / "gate.yaml"))


def load_arms(path: Path | None = None) -> dict[str, ArmConfig]:
    arms = [ArmConfig.model_validate(a) for a in _load(path or CONFIGS / "arms.yaml")]
    return {a.name: a for a in arms}


def load_models(path: Path | None = None) -> dict[str, ModelConfig]:
    models = [ModelConfig.model_validate(m) for m in _load(path or CONFIGS / "models.yaml")]
    return {m.name: m for m in models}


def scenarios_path() -> Path:
    return CONFIGS / "scenarios.yaml"


def load_scenarios(path: Path | None = None) -> dict[str, Scenario]:
    raw = _load(path or scenarios_path())
    out: dict[str, Scenario] = {}
    for item in raw:
        s = Scenario.model_validate(item)
        if s.id in out:
            raise ValueError(f"duplicate scenario id {s.id}")
        out[s.id] = s
    return out


def catalogue_sha(path: Path | None = None) -> str:
    return hashlib.sha256((path or scenarios_path()).read_bytes()).hexdigest()
