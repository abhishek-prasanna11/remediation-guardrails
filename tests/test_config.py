from rg.actions.catalogue import CATALOGUE, Proposal, Reversibility
from rg.config import load_arms, load_gate, load_models, load_topology
from rg.schema import EpisodeRecord, Label, StepRecord


def test_configs_load():
    topo = load_topology()
    assert len(topo.services) == 10
    gate = load_gate()
    assert set(gate.always_permitted) == {"no_op", "escalate_to_human", "gather_diagnostics"}
    for actions in gate.policy.values():
        assert set(actions) <= set(CATALOGUE)
    arms = load_arms()
    assert {"A0", "A1", "A2", "A2b", "A3", "A4"} <= set(arms)
    assert "none" in load_models()


def test_irreversibility_flags_match_plan_table():
    irreversible = {n for n, s in CATALOGUE.items() if s.reversibility is Reversibility.IRREVERSIBLE}
    assert irreversible == {"failover_database", "drain_node", "truncate_logs", "delete_files",
                            "flush_queue"}


def test_schema_roundtrip():
    step = StepRecord(step=1, attempt=0, tick=9, context_sha="x",
                      proposal=Proposal(action="restart_service", target="checkout"),
                      label=Label(unsafe=False, correct=True), verdict=None, executed=True,
                      health_before=0.8, health_after=0.9)
    ep = EpisodeRecord(episode_id="e", arm="A2", model="m", scenario_id="A1", family="A",
                       expected="fix", seed=0, catalogue_sha="s", outcome="recovered",
                       resolved=True, steps_used=1, final_health=1.0, trace_sha="t",
                       wallclock_s=0.1, steps=[step])
    assert EpisodeRecord.model_validate_json(ep.model_dump_json()) == ep
