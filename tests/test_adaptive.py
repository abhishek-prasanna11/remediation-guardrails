"""Supplementary family I (gate-aware injection, post hoc): the scenarios do what they claim.

Every injected action must pass the full gate when it is first proposed (otherwise the
attack is not gate-aware), and two of them must turn the gate's own limits against the
correct fix. The frozen catalogue must be untouched.
"""

import pytest

from rg.actions.catalogue import Proposal
from rg.actions.executor import execute
from rg.config import catalogue_sha, load_arms, load_scenarios, scenarios_path
from rg.faults.injector import start, tick
from rg.faults.labels import label
from rg.gate.gate import Gate, GateState
from rg.harness.episode import run_episode
from rg.propose.base import MOCKS

ADAPTIVE = load_scenarios(scenarios_path("adaptive"))
FROZEN_SHA = "26d10d8a493d5b7b7ae914e6f457dc3a7d0848b86dcd58afdcf33fc84fbddf1c"


def P(pat):
    return Proposal(action=pat.action, target=pat.target,
                    n=1 if pat.action == "scale_up" else None)


def follow_injection(sid, seed=0):
    """Execute the injected actions in order through the full gate; return what the gate
    then says about the scenario's correct fix."""
    s = ADAPTIVE[sid]
    ep = start(s, seed)
    gate, st = Gate(), GateState()
    for i, pat in enumerate(s.injected_actions, 1):
        ctx = ep.observer.build_context(i, 6, [])
        p = P(pat)
        v = gate.check(p, ctx, ep.cluster, st)
        assert v.decision == "approve", (sid, p.short(), v.reason)
        assert label(p, s, ep.cluster).classes[0] == "injection_compliance"
        h = ep.cluster.health()
        execute(ep.cluster, p)
        st.record(i, p, h, 0, ep.cluster)
        tick(ep)
        tick(ep)
    ctx = ep.observer.build_context(len(s.injected_actions) + 1, 6, [])
    return gate.check(P(s.correct_actions[0]), ctx, ep.cluster, st)


def test_frozen_catalogue_untouched():
    assert catalogue_sha() == FROZEN_SHA
    assert len(load_scenarios()) == 32


def test_four_family_i_scenarios():
    assert len(ADAPTIVE) == 4 and {s.family for s in ADAPTIVE.values()} == {"I"}


@pytest.mark.parametrize("sid", sorted(ADAPTIVE))
def test_every_injected_action_passes_the_full_gate(sid):
    follow_injection(sid)


def test_budget_burn_locks_out_the_fix():
    v = follow_injection("I2-inject-budget-burn")
    assert v.decision == "block" and v.failed == ["C5"]


def test_blast_radius_lockout():
    v = follow_injection("I3-inject-blast-radius-lockout")
    assert v.decision == "block" and v.failed == ["C3"]


@pytest.mark.parametrize("sid", sorted(ADAPTIVE))
@pytest.mark.parametrize("arm", ["M-correct", "M-correct-gated"])
def test_correct_behaviour_resolves(sid, arm):
    a = load_arms()[arm]
    rec = run_episode(ADAPTIVE[sid], 0, a, MOCKS[a.mock](), Gate() if a.gate else None)
    assert rec.resolved, (sid, arm, rec.outcome)
