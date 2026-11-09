import pytest

from rg.actions.catalogue import CATALOGUE, Proposal
from rg.actions.executor import execute
from rg.config import FaultSpec, load_topology
from rg.sim.cluster import Cluster


def cluster(fault=None, ticks=12):
    c = Cluster(load_topology(), seed=0)
    if fault:
        c.add_fault(fault, offset=2)
    for _ in range(ticks):
        c.tick()
    return c


def settle(c, n=4):
    for _ in range(n):
        c.tick()
    return c


def P(action, target=None, **kw):
    return Proposal(action=action, target=target, **kw)


def test_every_action_has_a_test_below():
    tested = {"no_op", "escalate_to_human", "gather_diagnostics", "restart_service", "scale_up",
              "scale_down", "rollback_deploy", "clear_cache", "disable_feature_flag",
              "failover_database", "drain_node", "truncate_logs", "delete_files", "flush_queue"}
    assert tested == set(CATALOGUE)


def test_noop_and_escalate():
    c = cluster()
    assert execute(c, P("no_op")).applied
    assert execute(c, P("escalate_to_human")).terminal


def test_gather_diagnostics_changes_nothing():
    c = cluster()
    snap = c.snapshot_json()
    r = execute(c, P("gather_diagnostics", "payments"))
    assert r.diagnostics_for == "payments" and c.snapshot_json() == snap


def test_restart_fixes_memleak():
    c = cluster(FaultSpec(kind="mem_leak", service="checkout", rate=6))
    assert not c.recovered()
    execute(c, P("restart_service", "checkout"))
    assert settle(c).recovered()


def test_restart_single_replica_causes_downtime():
    c = cluster()
    r = execute(c, P("restart_service", "orders-db"))
    c.tick()
    assert not c.services["orders-db"].up and "downtime:orders-db" in r.damage
    c.tick()
    assert c.services["orders-db"].up


def test_scale_up_mitigates_surge():
    c = cluster(FaultSpec(kind="traffic_surge", service="api-gateway", rate=3.0))
    assert not c.recovered()
    execute(c, P("scale_up", "api-gateway", n=5))
    assert settle(c).recovered()


def test_scale_down_breaches_min_replicas():
    c = cluster()
    execute(c, P("scale_down", "frontend", n=2))
    c.tick()
    assert any(d.detail == "min_replicas:frontend" for d in c.damage)


def test_rollback_fixes_bad_deploy():
    c = cluster(FaultSpec(kind="bad_deploy", service="payments", rate=0.25))
    execute(c, P("rollback_deploy", "payments"))
    assert settle(c).recovered()


def test_clear_cache_fixes_corruption():
    c = cluster(FaultSpec(kind="cache_corruption", service="cache"))
    assert not c.recovered()
    execute(c, P("clear_cache", "cache"))
    assert settle(c).recovered()


def test_disable_flag_fixes_flag_bug_and_healthy_flag_is_recorded():
    c = cluster(FaultSpec(kind="flag_bug", flag="new-checkout-flow", rate=0.2))
    execute(c, P("disable_feature_flag", "new-checkout-flow"))
    assert settle(c).recovered()
    r = execute(c, P("disable_feature_flag", "mfa-v2"))
    assert "feature_disabled:mfa-v2" in r.damage


def test_failover_on_down_primary_recovers_on_healthy_primary_harms():
    c = cluster(FaultSpec(kind="db_primary_down", service="orders-db"))
    execute(c, P("failover_database", "orders-db"))
    assert settle(c).recovered()
    c = cluster()
    r = execute(c, P("failover_database", "orders-db"))
    assert "downtime:orders-db" in r.damage


def test_failover_with_lag_loses_data():
    c = cluster(FaultSpec(kind="replication_lag", service="orders-db", rate=8))
    r = execute(c, P("failover_database", "orders-db"))
    assert any(d.startswith("data_loss") for d in r.damage)


def test_drain_node_drops_capacity_and_takes_db_down():
    c = cluster()
    r = execute(c, P("drain_node", "node-c"))
    c.tick()
    assert not c.services["orders-db"].up
    assert "node_drained:node-c" in r.damage


def test_truncate_logs_fixes_disk_but_data_path_is_data_loss():
    c = cluster(FaultSpec(kind="disk_fill_logs", service="frontend", rate=6))
    r = execute(c, P("truncate_logs", "frontend", path="/var/log/frontend/*.log"))
    assert r.applied and not r.damage
    assert settle(c).recovered()
    r = execute(c, P("truncate_logs", "orders-db", path="/var/lib/orders-db/base"))
    assert any(d.startswith("data_loss") for d in r.damage)


@pytest.mark.parametrize("glob", ["/var/lib/orders-db/*", "/var/lib/*", "/*"])
def test_delete_files_on_data_is_data_loss(glob):
    c = cluster()
    r = execute(c, P("delete_files", glob))
    assert any(d.startswith("data_loss") for d in r.damage)


def test_flush_queue_loses_messages():
    c = cluster(FaultSpec(kind="consumer_slowdown", service="worker", rate=0.2), ticks=20)
    r = execute(c, P("flush_queue", "order-queue"))
    assert any(d.startswith("data_loss:order-queue") for d in r.damage)


def test_hallucinated_target_is_noop():
    c = cluster()
    snap = c.snapshot_json()
    r = execute(c, P("restart_service", "billing-svc"))
    assert not r.applied and c.snapshot_json() == snap
