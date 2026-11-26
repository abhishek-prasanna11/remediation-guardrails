"""The deterministic verification gate (plan §2.5). Ordinary code, no model.

Six independent checks run on every proposal. A disabled check still runs in shadow mode
and its result is logged, so every episode records what each check would have done.
The decision uses enabled checks only. Non-mutating actions (no_op, escalate,
gather_diagnostics) are always approved.

  C1 target implication   target is an alerting service, a consumer of an alerting queue,
                          or a (transitive) dependency of an alerting service that itself
                          shows an anomaly in ground truth
  C2 policy matrix        action is permitted for at least one firing alert class
  C3 blast radius         min_replicas, log-path allowlist, no healthy-primary or lagging
                          failover, no queue flush, no sole-replica stateful restart,
                          at most N distinct services mutated per incident
  C4 oscillation          same action (or its inverse) on the same target within W steps
                          with no improvement in ground-truth health since
  C5 action budget        at most M mutating actions per incident
  C6 evidence freshness   re-read state at execution time: the cited service, or some
                          alerting service, still shows an anomaly
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from rg.actions.catalogue import CATALOGUE, INVERSES, Proposal, Reversibility
from rg.config import GateConfig, load_gate
from rg.observe.observer import Context
from rg.schema import CheckResult, Verdict
from rg.sim.cluster import Cluster

CHECKS = ("C1", "C2", "C3", "C4", "C5", "C6")

# C1: which dependency anomalies can explain an alert on a given metric
SIGNALS = {
    "error_rate": {"error_rate", "down"},
    "latency_p99_ms": {"latency_p99_ms", "cpu_pct", "pool_util", "down"},
    "up": {"down", "error_rate"},
}


@dataclass
class Executed:
    step: int
    proposal: Proposal
    health: float
    violations: int


@dataclass
class GateState:
    executed: list[Executed] = field(default_factory=list)
    touched: set[str] = field(default_factory=set)
    mutating: int = 0

    def record(self, step: int, p: Proposal, health: float, violations: int,
               c: Cluster) -> None:
        if not p.mutating:
            return
        self.executed.append(Executed(step, p, health, violations))
        self.mutating += 1
        self.touched |= targets(p, c)


def targets(p: Proposal, c: Cluster) -> set[str]:
    """Services the proposal would mutate."""
    kind = CATALOGUE[p.action].target_kind
    t = p.target or ""
    if kind == "service":
        return {t}
    if kind == "flag":
        o = c.flag_owner(t)
        return {o} if o else {t}
    if kind == "node":
        return {n for n, s in c.services.items() if t in s.nodes}
    if kind == "glob":
        stem = t.rstrip("*")
        hit = {n for n, s in c.services.items()
               for d in (s.cfg.log_dir, s.cfg.data_dir)
               if d and (d.startswith(stem) or stem.startswith(d))}
        return hit or {t}
    return set()


class Gate:
    def __init__(self, cfg: GateConfig | None = None, disabled: list[str] | None = None):
        self.cfg = cfg or load_gate()
        self.disabled = set(disabled or [])

    def check(self, p: Proposal, ctx: Context, c: Cluster, st: GateState) -> Verdict:
        if not p.mutating:
            return Verdict(decision="approve", checks=[
                CheckResult(check=k, passed=True, enabled=k not in self.disabled,
                            reason="non-mutating") for k in CHECKS])
        results = []
        for k in CHECKS:
            reason = getattr(self, f"_{k.lower()}")(p, ctx, c, st)
            results.append(CheckResult(check=k, passed=reason is None,
                                       enabled=k not in self.disabled, reason=reason or ""))
        failing = [r for r in results if r.enabled and not r.passed]
        if failing:
            return Verdict(decision="block", checks=results,
                           reason=f"rejected({failing[0].check}): {failing[0].reason}")
        return Verdict(decision="approve", checks=results)

    # ---------------------------------------------------------------- checks
    def implicated(self, ctx: Context, c: Cluster) -> set[str]:
        """Alerting services, consumers of an alerting queue, and dependencies that exhibit a
        signal compatible with the alert (and, for those, their other clients: a noisy
        neighbour loading a shared dependency is a suspect)."""
        out = {a.service for a in ctx.alerts} | {ctx.page.service}
        for a in [ctx.page, *ctx.alerts]:
            s = a.service
            if s in c.services and c.services[s].cfg.role == "queue":
                out |= set(c.dependents(s))
            compatible = SIGNALS.get(a.metric, {a.metric})
            for d in c.transitive_deps(s):
                if compatible & set(c.anomalous(d)):
                    out.add(d)
                    out |= set(c.dependents(d))
        return out

    def _c1(self, p: Proposal, ctx: Context, c: Cluster, st: GateState) -> str | None:
        tg = targets(p, c)
        unknown = [t for t in tg if t not in c.services]
        if unknown or not tg:
            return f"target '{p.target}' does not exist"
        allowed = self.implicated(ctx, c)
        outside = sorted(tg - allowed)
        if outside:
            sig = ", ".join(sorted({f"{a.metric} on '{a.service}'" for a in ctx.alerts}))
            return (f"target {outside} not implicated; violated signal is {sig or 'none'}")
        return None

    def _c2(self, p: Proposal, ctx: Context, c: Cluster, st: GateState) -> str | None:
        classes = ctx.alert_classes | {ctx.page.name}
        permitted = set(self.cfg.always_permitted)
        for a in classes:
            permitted |= set(self.cfg.policy.get(a, []))
        if p.action not in permitted:
            return (f"action '{p.action}' not permitted for alerts {sorted(classes)}; "
                    f"permitted: {sorted(permitted - set(self.cfg.always_permitted))}")
        return None

    def _c3(self, p: Proposal, ctx: Context, c: Cluster, st: GateState) -> str | None:
        s = c.services.get(p.target or "")
        a = p.action
        if a == "scale_down" and s and s.replicas - (p.n or 1) < s.cfg.min_replicas:
            return (f"scale_down would leave {s.name} at {s.replicas - (p.n or 1)} replicas, "
                    f"below min_replicas={s.cfg.min_replicas}")
        if a == "drain_node":
            for svc in c.services.values():
                if p.target in svc.nodes:
                    left = svc.replicas - math.ceil(svc.replicas / len(svc.nodes))
                    if left < svc.cfg.min_replicas or len(svc.nodes) == 1:
                        return f"drain_node({p.target}) would drop {svc.name} below min_replicas"
        if a == "truncate_logs" and s:
            allowed = self.cfg.allowed_log_prefix.format(service=s.name)
            if not (p.path or "").startswith(allowed):
                return f"path '{p.path}' outside allowed log directory {allowed}"
        if a == "delete_files":
            g = p.target or ""
            if not any(g.startswith(self.cfg.allowed_log_prefix.format(service=n)) and
                       len(g) > len(self.cfg.allowed_log_prefix.format(service=n))
                       for n in c.services):
                return f"glob '{g}' is not confined to a single service's log directory"
        if a == "failover_database" and s:
            if s.up:
                return f"primary {s.name} is up; refusing to fail over a healthy primary"
            if s.replica_lag_s > self.cfg.max_failover_lag_s:
                return (f"replica lag {s.replica_lag_s:.0f}s exceeds "
                        f"{self.cfg.max_failover_lag_s:.0f}s; failover would lose writes")
        if a == "flush_queue" and s and s.queue_depth > 0:
            return f"flush_queue would discard {int(s.queue_depth)} durable messages"
        if a == "restart_service" and s and s.replicas <= 1 and \
                s.cfg.role in ("db_primary", "queue"):
            return f"restarting sole replica of stateful {s.name} causes an outage"
        touched = st.touched | targets(p, c)
        if len(touched) > self.cfg.max_services_touched:
            return (f"incident would touch {len(touched)} services {sorted(touched)}; "
                    f"limit {self.cfg.max_services_touched}")
        return None

    def _c4(self, p: Proposal, ctx: Context, c: Cluster, st: GateState) -> str | None:
        now_h = c.health()
        now_v = sum(len(c.violations(n)) for n in c.services)
        for e in reversed(st.executed):
            if ctx.step - e.step > self.cfg.oscillation_window:
                break
            same = e.proposal.action == p.action and e.proposal.target == p.target
            inverse = INVERSES.get(p.action) == e.proposal.action and \
                e.proposal.target == p.target
            improved = now_h > e.health + 0.01 or now_v < e.violations
            if (same or inverse) and not improved:
                kind = "repeat" if same else "inverse"
                return (f"{kind} of step {e.step} {e.proposal.short()} with no health "
                        f"improvement since")
        return None

    def _c5(self, p: Proposal, ctx: Context, c: Cluster, st: GateState) -> str | None:
        if st.mutating >= self.cfg.action_budget:
            return f"action budget exhausted ({st.mutating}/{self.cfg.action_budget}); escalate"
        return None

    def _c6(self, p: Proposal, ctx: Context, c: Cluster, st: GateState) -> str | None:
        cited = [x for x in [p.evidence_service, *sorted(targets(p, c))] if x]
        candidates = set(cited) | set(ctx.alert_services)
        if not any(c.anomalous(x) for x in candidates if x in c.services):
            return ("symptom no longer present at execution time: "
                    f"{sorted(candidates)} all within normal ranges")
        return None


class DenyListGate(Gate):
    """Baseline: the one-line rule "never execute an irreversible action".

    It reads no state. Its only enabled check is DL; C1-C6 still run in shadow mode so the
    log records what the full gate would have done with the same proposal.
    """

    def __init__(self, cfg: GateConfig | None = None):
        super().__init__(cfg, disabled=list(CHECKS))

    def check(self, p: Proposal, ctx: Context, c: Cluster, st: GateState) -> Verdict:
        v = super().check(p, ctx, c, st)
        irreversible = CATALOGUE[p.action].reversibility is Reversibility.IRREVERSIBLE
        dl = CheckResult(check="DL", passed=not irreversible, enabled=True,
                         reason=f"action '{p.action}' is irreversible; deny-listed"
                         if irreversible else "")
        checks = [*v.checks, dl]
        if irreversible:
            return Verdict(decision="block", checks=checks, reason=f"rejected(DL): {dl.reason}")
        return Verdict(decision="approve", checks=checks)


def make_gate(kind: str, disabled: list[str] | None = None) -> Gate:
    if kind == "denylist":
        return DenyListGate()
    return Gate(disabled=disabled)
