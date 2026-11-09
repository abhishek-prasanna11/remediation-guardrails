"""Builds a ready-to-decide episode from a scenario and a seed."""

from __future__ import annotations

from dataclasses import dataclass

from rg.config import Scenario, Topology, load_topology
from rg.observe.observer import Observer
from rg.sim.cluster import Cluster

WARMUP = 5
MAX_WAIT = 40


class NoAlert(RuntimeError):
    pass


@dataclass
class Episode:
    scenario: Scenario
    seed: int
    cluster: Cluster
    observer: Observer


def tick(ep: Episode) -> None:
    ep.cluster.tick()
    ep.observer.observe()


def start(scenario: Scenario, seed: int, topology: Topology | None = None) -> Episode:
    c = Cluster(topology or load_topology(), seed=seed)
    o = Observer(c, seed=seed, injections=scenario.injections, decoys=scenario.decoys,
                 obscure_logs=scenario.obscure_logs)
    ep = Episode(scenario, seed, c, o)
    for _ in range(WARMUP):
        tick(ep)
    for f in scenario.faults:
        c.add_fault(f, offset=c.t + 1)
    for d in scenario.decoys:
        c.decoys[(d.service, d.metric)] = d.value
    for s in c.services.values():
        if s.cfg.role == "db_primary":
            s.replica_lag_s = scenario.replica_lag_s
    for _ in range(MAX_WAIT):
        tick(ep)
        if o.page_alert is not None:
            break
    if o.page_alert is None:
        raise NoAlert(f"{scenario.id}: no alert fired within {MAX_WAIT} ticks")
    for _ in range(scenario.page_delay):
        tick(ep)
    return ep
