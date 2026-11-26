"""Statistics: zero-event intervals and the scenario-level paired test."""

import pandas as pd
import pytest

from rg.analysis.metrics import cluster_boot, exact_zero_upper, paired


def episodes(arm, outcomes):
    """outcomes: {scenario: [value per seed]} -> episode rows for one arm."""
    return [{"arm": arm, "model": "m", "scenario_id": s, "seed": i, "x": v}
            for s, vals in outcomes.items() for i, v in enumerate(vals)]


def test_exact_zero_upper_matches_clopper_pearson():
    assert exact_zero_upper(32) == pytest.approx(0.1089, abs=1e-4)
    assert exact_zero_upper(0) == 1.0


def test_zero_event_rate_gets_exact_upper_bound_over_clusters():
    df = pd.DataFrame(episodes("a", {f"s{i}": [0, 0, 0] for i in range(32)}))
    est = cluster_boot(df, "x")
    assert est.value == 0 and est.lo == 0
    assert est.hi == pytest.approx(exact_zero_upper(32))  # 32 clusters, not 96 episodes


def test_all_event_rate_gets_exact_lower_bound():
    df = pd.DataFrame(episodes("a", {f"s{i}": [1, 1] for i in range(32)}))
    est = cluster_boot(df, "x")
    assert est.value == 1 and est.lo == pytest.approx(1 - exact_zero_upper(32))


def test_difference_is_not_treated_as_a_rate():
    df = pd.DataFrame({"scenario_id": ["s1", "s2"], "d": [0.0, 0.0]})
    est = cluster_boot(df, "d", rate=False)
    assert (est.lo, est.hi) == (0.0, 0.0)


def test_sign_test_counts_scenarios_not_seeds():
    # one scenario flips in all 15 seeds: McNemar sees 15 discordant pairs, but it is a
    # single scenario, so the scenario-level test cannot reject
    a = {f"s{i}": [0] * 15 for i in range(32)}
    b = {**a, "s0": [1] * 15}
    E = pd.DataFrame(episodes("A", a) + episodes("B", b))
    r = paired(E, "A", "B", "m", "x")
    assert r["n01"] == 15 and r["p_mcnemar"] < 1e-4
    assert (r["s_up"], r["s_down"]) == (1, 0) and r["p"] == 1.0


def test_sign_test_rejects_consistent_change_across_scenarios():
    a = {f"s{i}": [1, 1, 1] for i in range(13)}
    b = {f"s{i}": [0, 0, 0] for i in range(13)}
    E = pd.DataFrame(episodes("A", a) + episodes("B", b))
    r = paired(E, "A", "B", "m", "x")
    assert (r["s_up"], r["s_down"]) == (0, 13)
    assert r["p"] == pytest.approx(2 * 0.5 ** 13)


def test_kappa_is_exact_at_a_rounding_tie():
    # 71/80 agreement with pe = 1/2 gives kappa = 0.775 exactly; it must print as 0.78
    from rg.analysis.irr import kappa
    mech = pd.Series([0] * 40 + [1] * 40)
    rater = pd.Series([0] * 31 + [1] * 9 + [1] * 40)
    assert f"{kappa(rater, mech):.2f}" == "0.78"


def test_irr_numbers_report_first_pass_and_revision(tmp_path, monkeypatch):
    import rg.analysis.report as report
    pd.DataFrame({"row": [1, 2, 3, 4], "rater_unsafe": [1, 1, 0, 0],
                  "rater_revised": [1, 0, 0, 0]}).to_csv(tmp_path / "irr_sheet.csv", index=False)
    pd.DataFrame({"row": [1, 2, 3, 4], "unsafe": [True, False, False, False]}).to_csv(
        tmp_path / "irr_key.csv", index=False)
    monkeypatch.setattr(report, "DER", tmp_path)
    m = dict(report.irr_numbers())
    assert (m["IrrAgree"], m["IrrDisagree"]) == ("75", "1")
    assert (m["IrrAgreeRevised"], m["IrrKappaRevised"], m["IrrRevised"]) == ("100.0", "1.00", "1")
