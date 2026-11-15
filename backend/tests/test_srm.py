"""算法 A（SRM + 功效）：正常 / 边界 / 确定性。"""
from __future__ import annotations

import pytest

from src.services.algorithms import srm, stats


def _variants(control=3138, treat=2862, ratio=0.5):
    return [
        {"code": "control", "name": "对照", "ratio": ratio, "observed": control, "is_control": True},
        {"code": "treat", "name": "实验", "ratio": 1 - ratio, "observed": treat, "is_control": False},
    ]


def test_srm_flags_50_50_drift():
    """验收场景：计划 50/50，实测 52.3% / 47.7%（合计 6,000）→ χ²≈12.7，p≈0.0004，告警。"""
    result = srm.run_srm(_variants(), baseline_rate=0.101, planned_mde=0.011)
    assert result["total"] == 6000
    assert result["df"] == 1
    assert result["chi2"] == pytest.approx(12.696, abs=1e-3)
    assert result["p_value"] == pytest.approx(0.000366, abs=1e-5)
    assert result["alarm"] is True
    assert result["status"] == "srm"
    shares = [cell["share_pct"] for cell in result["cells"]]
    assert shares == pytest.approx([52.3, 47.7], abs=0.01)
    # 单格贡献 = (obs-exp)²/exp = 6.348，两格合计 12.696
    assert result["cells"][0]["contribution"] == pytest.approx(6.348, abs=1e-3)


def test_srm_balanced_split_not_flagged():
    result = srm.run_srm(_variants(3000, 3000), baseline_rate=0.1, planned_mde=0.01)
    assert result["chi2"] == 0.0
    assert result["p_value"] == 1.0
    assert result["alarm"] is False
    assert result["status"] == "balanced"


def test_srm_three_variants_df_and_power_gap():
    variants = [
        {"code": "a", "ratio": 0.34, "observed": 4000, "is_control": True},
        {"code": "b", "ratio": 0.33, "observed": 4002},
        {"code": "c", "ratio": 0.33, "observed": 3998},
    ]
    result = srm.run_srm(variants, baseline_rate=0.048, planned_mde=0.013)
    assert result["df"] == 2
    assert result["alarm"] is False
    assert result["required_per_variant"] > 0
    assert 0.0 <= result["power_at_current"] <= 1.0
    assert len(result["gap_per_variant"]) == 3


def test_srm_power_gap_when_underpowered():
    """只有 3,000/变体时，检测 1.1pp 效应所需样本约 11,780，缺口为正。"""
    result = srm.run_srm(_variants(3000, 3000), baseline_rate=0.101, planned_mde=0.011)
    assert result["required_per_variant"] == 11780
    assert result["gap_per_variant"] == [8780, 8780]
    assert result["power_at_current"] < 0.8


def test_srm_rejects_empty_and_negative():
    with pytest.raises(ValueError):
        srm.run_srm([])
    with pytest.raises(ValueError):
        srm.run_srm(_variants(0, 0))
    with pytest.raises(ValueError):
        srm.run_srm([
            {"code": "a", "ratio": 0.5, "observed": -1},
            {"code": "b", "ratio": 0.5, "observed": 10},
        ])


def test_srm_deterministic():
    first = srm.run_srm(_variants(), baseline_rate=0.101, planned_mde=0.011)
    second = srm.run_srm(_variants(), baseline_rate=0.101, planned_mde=0.011)
    assert first == second


def test_stats_chi2_and_normal_helpers():
    assert stats.chi2_sf(3.8415, 1) == pytest.approx(0.05, abs=1e-4)
    assert stats.chi2_sf(5.9915, 2) == pytest.approx(0.05, abs=1e-4)
    assert stats.norm_ppf(0.975) == pytest.approx(1.959964, abs=1e-6)
    assert stats.norm_cdf(0.0) == pytest.approx(0.5, abs=1e-12)
    assert stats.required_sample_per_variant(0.101, 0.011) == 11780
    assert stats.achieved_power(11780, 0.101, 0.011) == pytest.approx(0.8, abs=0.01)
