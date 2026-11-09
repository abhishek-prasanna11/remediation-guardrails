from rg.config import FaultSpec, load_topology
from rg.sim.cluster import Cluster


def run(seed: int, fault: FaultSpec | None = None, ticks: int = 25) -> Cluster:
    c = Cluster(load_topology(), seed=seed)
    if fault:
        c.add_fault(fault, offset=5)
    for _ in range(ticks):
        c.tick()
    return c


def test_same_seed_byte_identical_trace():
    f = FaultSpec(kind="mem_leak", service="checkout", rate=4)
    a, b = run(7, f), run(7, f)
    assert a.trace == b.trace
    assert a.trace_sha() == b.trace_sha()


def test_different_seed_different_trace():
    assert run(1).trace_sha() != run(2).trace_sha()


def test_healthy_baseline_stays_healthy():
    c = run(3, ticks=40)
    assert c.recovered()
    assert c.health() > 0.99


def test_memory_leak_grows_and_cascades_to_callers():
    c = run(0, FaultSpec(kind="mem_leak", service="checkout", rate=6), ticks=15)
    assert "mem_pct" in c.violations("checkout")
    assert c.violations("api-gateway")  # caller sees the errors
    assert not c.recovered()


def test_dependency_down_propagates_errors():
    c = run(0, FaultSpec(kind="db_primary_down", service="orders-db"), ticks=8)
    assert c.violations("orders-db") == ["down"]
    assert "error_rate" in c.violations("checkout")
    assert "error_rate" in c.violations("worker")


def test_transient_fault_self_resolves():
    c = run(0, FaultSpec(kind="traffic_surge", service="api-gateway", rate=3.2, duration=3),
            ticks=12)
    assert c.recovered()


def test_min_replica_invariant_recorded():
    c = run(0, ticks=2)
    c.services["frontend"].replicas = 1
    c.tick()
    assert any(d.detail == "min_replicas:frontend" for d in c.damage)
