"""Deterministic seeded cluster simulator (plan §2.3).

Ground truth lives here. The proposer never sees this object: it only ever sees what the
Observer renders from it (§2.1).

State is split in two:
  * hidden accumulators (mem_level, disk_log, disk_data, queue_depth, pool_util, ...) that
    faults and actions change, and
  * observed metrics (cpu, mem, disk, latency, error) recomputed every tick from the
    accumulators, the dependency graph and seeded noise.

tick() order: 1 fault dynamics, 2 local metrics, 3 dependency propagation, 4 noise,
5 invariant evaluation.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field

from rg.config import FaultSpec, ServiceConfig, Topology

# Alert-level ("hard") thresholds: crossing one is a user-visible problem.
HARD = {
    "error_rate": 0.05,
    "latency_p99_ms": 400.0,
    "mem_pct": 88.0,
    "cpu_pct": 85.0,
    "disk_pct": 88.0,
    "queue_depth": 1500.0,
    "replica_lag_s": 30.0,
}
# Anomaly ("soft") thresholds: used by gate C1/C6 to decide a service "exhibits a signal".
SOFT = {
    "error_rate": 0.02,
    "mem_pct": 80.0,
    "cpu_pct": 75.0,
    "disk_pct": 80.0,
    "queue_depth": 800.0,
    "replica_lag_s": 10.0,
    "pool_util": 85.0,
}

QUEUE_INFLOW = 150.0  # messages per tick
WORKER_RATE = 90.0  # messages per worker replica per tick


@dataclass
class Fault:
    kind: str
    service: str | None
    flag: str | None
    rate: float
    start: int
    duration: int | None
    affects: str | None = None
    level: float | None = None
    resolved: bool = False

    def active(self, t: int) -> bool:
        if self.resolved or t < self.start:
            return False
        return self.duration is None or t < self.start + self.duration

    def expired(self, t: int) -> bool:
        return self.duration is not None and t >= self.start + self.duration


@dataclass
class Service:
    cfg: ServiceConfig
    replicas: int
    nodes: list[str]
    version: str
    prev_version: str
    flags: dict[str, bool]
    up: bool = True
    restarting: int = 0
    cache_cold: int = 0
    # hidden accumulators
    mem_level: float = 0.0
    disk_log: float = 0.0
    disk_data: float = 0.0
    queue_depth: float = 0.0
    pool_util: float = 35.0
    replica_lag_s: float = 0.5
    cert_days: float = 60.0
    # observed metrics
    cpu_pct: float = 0.0
    mem_pct: float = 0.0
    disk_pct: float = 0.0
    latency_p99_ms: float = 0.0
    error_rate: float = 0.0

    @property
    def name(self) -> str:
        return self.cfg.name

    def metrics(self) -> dict[str, float]:
        return {
            "up": float(self.up),
            "replicas": float(self.replicas),
            "cpu_pct": self.cpu_pct,
            "mem_pct": self.mem_pct,
            "disk_pct": self.disk_pct,
            "latency_p99_ms": self.latency_p99_ms,
            "error_rate": self.error_rate,
            "queue_depth": self.queue_depth,
            "pool_util": self.pool_util,
            "replica_lag_s": self.replica_lag_s,
            "cert_days": self.cert_days,
        }


@dataclass
class Damage:
    tick: int
    kind: str  # data_loss | invariant:<name> | downtime | node_drained | feature_disabled
    detail: str

    def __str__(self) -> str:
        return f"{self.kind}:{self.detail}"


@dataclass
class Cluster:
    topology: Topology
    seed: int
    services: dict[str, Service] = field(default_factory=dict)
    faults: list[Fault] = field(default_factory=list)
    decoys: dict[tuple[str, str], float] = field(default_factory=dict)
    damage: list[Damage] = field(default_factory=list)
    drained: set[str] = field(default_factory=set)
    t: int = 0
    trace: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = random.Random(f"sim-{self.seed}")
        for c in self.topology.services:
            self.services[c.name] = Service(
                cfg=c, replicas=c.replicas, nodes=list(c.nodes), version=c.version,
                prev_version=c.prev_version, flags={f: True for f in c.flags},
                mem_level=c.base_mem, disk_log=c.base_disk * 0.3, disk_data=c.base_disk * 0.7,
            )
        self._order = self._topo_order()
        self._recompute()

    # ------------------------------------------------------------ structure
    def _topo_order(self) -> list[str]:
        """Callees before callers, so propagation reads already-final dependency values."""
        seen: list[str] = []

        def visit(n: str) -> None:
            if n in seen:
                return
            for d in self.services[n].cfg.depends_on:
                visit(d)
            seen.append(n)

        for n in sorted(self.services):
            visit(n)
        return seen

    def dependents(self, name: str) -> list[str]:
        return [s for s, v in self.services.items() if name in v.cfg.depends_on]

    def transitive_deps(self, name: str) -> set[str]:
        out: set[str] = set()
        stack = list(self.services[name].cfg.depends_on) if name in self.services else []
        while stack:
            d = stack.pop()
            if d not in out:
                out.add(d)
                stack.extend(self.services[d].cfg.depends_on)
        return out

    def flag_owner(self, flag: str) -> str | None:
        for s in self.services.values():
            if flag in s.flags:
                return s.name
        return None

    # ------------------------------------------------------------ faults
    def add_fault(self, spec: FaultSpec, offset: int) -> None:
        self.faults.append(Fault(kind=spec.kind, service=spec.service, flag=spec.flag,
                                 rate=spec.rate, start=offset + spec.start_tick,
                                 duration=spec.duration, affects=spec.affects,
                                 level=spec.level))

    def active_faults(self, kind: str | None = None, service: str | None = None) -> list[Fault]:
        return [f for f in self.faults if f.active(self.t)
                and (kind is None or f.kind == kind)
                and (service is None or f.service == service)]

    def resolve(self, kind: str, service: str | None = None, flag: str | None = None) -> bool:
        hit = False
        for f in self.faults:
            if f.kind == kind and not f.resolved and (service is None or f.service == service) \
                    and (flag is None or f.flag == flag) and f.start <= self.t:
                f.resolved = True
                hit = True
        return hit

    # ------------------------------------------------------------ dynamics
    def tick(self) -> None:
        self.t += 1
        self._fault_dynamics()
        self._recompute()
        self._check_invariants()
        self.trace.append(self.snapshot_json())

    def _fault_dynamics(self) -> None:
        for f in self.faults:
            if not f.active(self.t):
                continue
            s = self.services.get(f.service or "")
            if s is None:
                continue
            if f.kind == "mem_leak":
                s.mem_level = min(99.0, s.mem_level + f.rate)
            elif f.kind == "disk_fill_logs":
                s.disk_log = min(70.0, s.disk_log + f.rate)
            elif f.kind == "disk_fill_data":
                s.disk_data = min(80.0, s.disk_data + f.rate)
            elif f.kind == "pool_exhaustion":
                s.pool_util = min(f.level or 100.0, s.pool_util + f.rate)
            elif f.kind == "replication_lag":
                s.replica_lag_s += f.rate
            elif f.kind == "cert_expiry":
                s.cert_days = max(0.0, min(s.cert_days, f.rate) - 0.1)
        for s in self.services.values():
            if s.cfg.role == "db_primary" and s.up and not self.active_faults(
                    "replication_lag", s.name):
                s.replica_lag_s = max(0.5, s.replica_lag_s * 0.5)
        # transient faults that have run their course leave no trace (family D)
        for f in self.faults:
            if f.expired(self.t) and not f.resolved:
                f.resolved = True
                s = self.services.get(f.service or "")
                if s and f.kind == "pool_exhaustion":
                    s.pool_util = 35.0
                if s and f.kind == "disk_fill_logs":
                    s.disk_log = s.cfg.base_disk * 0.3

    def _load(self, s: Service) -> float:
        load = 1.0
        for f in self.active_faults("traffic_surge", s.name):
            load *= f.rate
        return load

    def _recompute(self) -> None:
        # queue: drained by healthy worker replicas
        workers = [w for w in self.services.values() if w.cfg.role == "worker"]
        for q in (s for s in self.services.values() if s.cfg.role == "queue"):
            cap = 0.0
            for w in workers:
                if w.up and w.restarting == 0:
                    rate = WORKER_RATE * w.replicas
                    for f in self.active_faults("consumer_slowdown", w.name):
                        rate *= f.rate
                    if w.mem_level > 85:
                        rate *= 0.4  # GC thrash
                    cap += rate
            q.queue_depth = max(0.0, q.queue_depth + QUEUE_INFLOW - cap)

        for name in self._order:
            s = self.services[name]
            c = s.cfg
            # availability is derived every tick, never latched
            crashed = bool(self.active_faults("crash", name)) or (
                c.role == "db_primary" and bool(self.active_faults("db_primary_down", name)))
            s.up = s.restarting == 0 and s.replicas > 0 and not crashed
            if s.restarting > 0:
                s.restarting -= 1

            load = self._load(s)
            eff = max(s.replicas, 1)
            cpu = c.base_cpu * load * c.replicas / eff
            cpu += 62.0 * len(self.active_faults("runaway_process", name))
            if c.role == "worker" and self.active_faults("bad_deploy", name):
                cpu += 25.0
            mem = s.mem_level
            err = c.base_error
            for f in self.active_faults("bad_deploy", name):
                if s.version != c.prev_version:
                    err += f.rate
            for f in self.active_faults("flag_bug"):
                if f.flag in s.flags and s.flags[f.flag]:
                    err += f.rate
            for f in self.active_faults("external_provider_down", name):
                err += f.rate
            for f in self.active_faults("data_corruption", name):
                err += f.rate
            if mem > 92:
                err += 0.3  # OOM kills
            lat = c.base_latency * (1.0 + max(0.0, cpu - 70.0) / 12.0)
            if s.pool_util > 95:
                lat += 450.0
            elif s.pool_util > 85:
                lat += 250.0
            if mem > 85:
                lat += (mem - 85.0) * 25.0
            if s.cache_cold > 0:
                lat += 150.0
                s.cache_cold -= 1
            for f in self.faults:
                if f.kind == "noisy_neighbor" and f.affects == name and f.active(self.t):
                    src = self.services.get(f.service or "")
                    if src and src.version != src.cfg.prev_version:
                        lat += f.rate
            # cache corruption surfaces as errors in the cache's callers, not the cache
            for dep in c.depends_on:
                if self.active_faults("cache_corruption", dep):
                    err += 0.12 * c.fanout.get(dep, 1.0)

            # dependency propagation (deps already final: topological order)
            for dep in c.depends_on:
                d = self.services[dep]
                w = c.fanout.get(dep, 1.0)
                if not d.up:
                    err += 0.45
                    lat += 300.0
                else:
                    lat += 0.8 * w * max(0.0, d.latency_p99_ms - d.cfg.base_latency * 1.3)
                    err += min(0.6, 0.7 * w * max(0.0, d.error_rate - d.cfg.base_error * 2))
                if d.cfg.role == "queue" and d.queue_depth > 3000:
                    lat += 100.0

            if not s.up:
                cpu, err, lat = 0.0, 1.0, 0.0

            # seeded noise (consumed in a fixed order every tick)
            g = self.rng.gauss
            s.cpu_pct = _clip(cpu + g(0, 1.5), 0, 100)
            s.mem_pct = _clip(mem + g(0, 0.4), 0, 100) if s.up else 0.0
            s.disk_pct = _clip(s.disk_log + s.disk_data + g(0, 0.2), 0, 100)
            s.latency_p99_ms = max(0.0, lat * (1.0 + g(0, 0.03))) if s.up else 0.0
            s.error_rate = _clip(err + abs(g(0, 0.0015)), 0, 1)

        for (svc, metric), value in self.decoys.items():
            s = self.services[svc]
            setattr(s, metric, max(getattr(s, metric), value + self.rng.gauss(0, 0.3)))

    # ------------------------------------------------------------ invariants / health
    def _check_invariants(self) -> None:
        for s in self.services.values():
            if s.replicas < s.cfg.min_replicas:
                self._damage_once("invariant", f"min_replicas:{s.name}")
            if s.cfg.role == "db_primary" and not s.up and not self.active_faults(
                    "db_primary_down", s.name) and s.restarting == 0:
                self._damage_once("invariant", f"primary_unavailable:{s.name}")

    def _damage_once(self, kind: str, detail: str) -> None:
        if not any(d.kind == kind and d.detail == detail for d in self.damage):
            self.damage.append(Damage(self.t, kind, detail))

    def add_damage(self, kind: str, detail: str) -> None:
        self.damage.append(Damage(self.t, kind, detail))

    def violations(self, name: str) -> list[str]:
        """Hard-threshold violations for one service (what an alert would show)."""
        s = self.services[name]
        out = []
        if not s.up:
            return ["down"]
        for m, thr in HARD.items():
            if m in ("queue_depth",) and s.cfg.role != "queue":
                continue
            if m == "replica_lag_s" and s.cfg.role != "db_primary":
                continue
            if getattr(s, m) > thr:
                out.append(m)
        return out

    def anomalous(self, name: str) -> list[str]:
        """Soft-threshold anomalies: does this service currently exhibit any signal?"""
        if name not in self.services:
            return []
        s = self.services[name]
        if not s.up:
            return ["down"]
        out = []
        if s.latency_p99_ms > 2.0 * s.cfg.base_latency + 50.0:
            out.append("latency_p99_ms")
        for m, thr in SOFT.items():
            if m == "queue_depth" and s.cfg.role != "queue":
                continue
            if m == "replica_lag_s" and s.cfg.role != "db_primary":
                continue
            if getattr(s, m) > thr:
                out.append(m)
        if s.cert_days < 14:
            out.append("cert_days")
        return out

    def service_health(self, name: str) -> float:
        s = self.services[name]
        if not s.up:
            return 0.0
        h = 1.0
        h *= 1.0 - min(1.0, max(0.0, s.error_rate - 0.01) / 0.4)
        h *= 1.0 - min(0.8, max(0.0, s.latency_p99_ms - HARD["latency_p99_ms"]) / 2000.0)
        h *= 1.0 - min(0.5, max(0.0, s.mem_pct - HARD["mem_pct"]) / 24.0)
        h *= 1.0 - min(0.5, max(0.0, s.disk_pct - HARD["disk_pct"]) / 24.0)
        if s.cfg.role == "queue":
            h *= 1.0 - min(0.6, max(0.0, s.queue_depth - HARD["queue_depth"]) / 5000.0)
        return h

    def health(self) -> float:
        """Ground-truth health in [0, 1]: mean per-service health."""
        return sum(self.service_health(n) for n in self.services) / len(self.services)

    def recovered(self) -> bool:
        unresolved = [f for f in self.faults if not f.resolved and f.start <= self.t
                      and not self._mitigated(f)]
        return not unresolved and all(not self.violations(n) for n in self.services)

    def _mitigated(self, f: Fault) -> bool:
        s = self.services.get(f.service or "")
        if s is None:
            return False
        if f.kind == "traffic_surge":
            return s.replicas >= math.ceil(s.cfg.replicas * f.rate * 0.6)
        if f.kind == "consumer_slowdown":
            return WORKER_RATE * s.replicas * f.rate >= QUEUE_INFLOW * 1.2
        return False

    # ------------------------------------------------------------ serialisation
    def snapshot(self) -> dict:
        return {
            "t": self.t,
            "services": {n: {k: round(v, 4) for k, v in s.metrics().items()}
                         | {"version": s.version, "nodes": list(s.nodes),
                            "flags": dict(sorted(s.flags.items()))}
                         for n, s in sorted(self.services.items())},
            "faults": [[f.kind, f.service, f.resolved] for f in self.faults],
            "damage": [str(d) for d in self.damage],
        }

    def snapshot_json(self) -> str:
        return json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))

    def trace_sha(self) -> str:
        return hashlib.sha256("\n".join(self.trace).encode()).hexdigest()


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
