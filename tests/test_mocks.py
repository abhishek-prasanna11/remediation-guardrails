"""Phase 4: each mock reproduces its failure mode deterministically (no gate)."""

import pytest

from rg.config import load_arms, load_scenarios
from rg.harness.episode import run_episode
from rg.propose.base import MOCKS

SCEN = load_scenarios()
ARMS = load_arms()


def run(mock, sid, seed=0, gated=False):
    from rg.gate.gate import Gate

    arm = ARMS[f"M-{mock}" + ("-gated" if gated else "")]
    return run_episode(SCEN[sid], seed, arm, MOCKS[mock](), Gate() if gated else None)


def classes(rec):
    return {c for s in rec.steps if s.executed for c in s.label.classes}


@pytest.mark.parametrize("sid", sorted(SCEN))
def test_correct_mock_resolves_every_scenario(sid):
    assert run("correct", sid).resolved


def test_hallucinator_hits_wrong_target():
    rec = run("hallucinator", "A1-memleak-checkout")
    assert "wrong_target" in classes(rec) and not rec.resolved


def test_over_reacher_is_catastrophic():
    rec = run("over_reacher", "A1-memleak-checkout")
    assert rec.outcome == "catastrophic"
    assert "destructive_overreach" in classes(rec)


def test_oscillator_alternates():
    rec = run("oscillator", "A1-memleak-checkout")
    acts = [s.proposal.action for s in rec.steps]
    assert acts[:4] == ["scale_up", "scale_down", "scale_up", "scale_down"]


@pytest.mark.parametrize("sid", [s for s in SCEN if s.startswith("F")])
def test_injection_follower_complies(sid):
    rec = run("injection_follower", sid)
    assert "injection_compliance" in classes(rec)


@pytest.mark.parametrize("mock", sorted(MOCKS))
def test_mocks_are_deterministic(mock):
    a, b = run(mock, "F2-inject-drain-annotation", 3), run(mock, "F2-inject-drain-annotation", 3)
    assert a.model_dump(exclude={"wallclock_s"}) == b.model_dump(exclude={"wallclock_s"})
