"""算法 B（双比例检验 + 多重校正）：正常 / 边界 / 确定性。"""
from __future__ import annotations

import pytest

from src.services.algorithms import metric_test


def _metric(key="order_rate", name="下单转化率", n1=10208, c1=1142, n2=10200, c2=1029, primary=True):
    return {
        "metric_key": key,
        "metric_name": name,
        "is_primary": primary,
        "control": {"n": n2, "conversions": c2},
        "variant": {"code": "treat", "name": "实验", "n": n1, "conversions": c1},
    }


def _family():
    return [
        _metric(),
        _metric("cart_rate", "加购转化率", c1=1787, c2=1735, primary=False),
        _metric("retention_d1", "次日留存", c1=3122, c2=3170, primary=False),
        _metric("click_rate", "点击率", c1=2235, c2=2173, primary=False),
    ]


def test_two_proportion_primary_metric():
    result = metric_test.run_metric_tests(_family(), method="bh")
    primary = result["primary"]
    assert primary["control_rate"] == pytest.approx(0.100882, abs=1e-6)
    assert primary["variant_rate"] == pytest.approx(0.111873, abs=1e-6)
    assert primary["lift"] == pytest.approx(0.1089, abs=1e-3)
    assert primary["p_value"] == pytest.approx(0.0109, abs=1e-3)
    # BH: 4 个指标里最小 p 排第 1，q = 4p
    assert primary["q_bh"] == pytest.approx(primary["p_value"] * 4, abs=1e-6)
    assert primary["significant"] is True
    assert primary["verdict"] == "ship"
    assert primary["ci_low"] < primary["diff"] < primary["ci_high"]


def test_bonferroni_more_conservative_than_bh():
    family = _family()
    bonf = metric_test.run_metric_tests(family, method="bonferroni")["primary"]
    bh = metric_test.run_metric_tests(family, method="bh")["primary"]
    assert bonf["q_bonferroni"] == pytest.approx(bonf["p_value"] * 4, abs=1e-6)
    assert bonf["q_value"] == pytest.approx(bonf["q_bonferroni"], abs=1e-9)
    assert bh["q_value"] <= bonf["q_value"] + 1e-12


def test_negative_effect_verdict_is_stop():
    """显著负向（次日留存 -2.2pp）→ 停止。"""
    metrics = [
        _metric("retention_d1", "次日留存", n1=8000, c1=2072, n2=8000, c2=2248),
    ]
    result = metric_test.run_metric_tests(metrics, method="bh")
    primary = result["primary"]
    assert primary["lift"] < 0
    assert primary["p_value"] < 0.01
    assert primary["verdict"] == "stop"
    assert primary["ci_high"] < 0


def test_not_significant_verdict_is_continue():
    metrics = [_metric(n1=6000, c1=516, n2=6000, c2=498)]
    primary = metric_test.run_metric_tests(metrics, method="bh")["primary"]
    assert primary["significant"] is False
    assert primary["verdict"] == "continue"


def test_identity_data_has_zero_z():
    metrics = [_metric(n1=5000, c1=500, n2=5000, c2=500)]
    primary = metric_test.run_metric_tests(metrics)["primary"]
    assert primary["z"] == 0.0
    assert primary["p_value"] == 1.0
    assert primary["lift"] == 0.0
    assert primary["verdict"] == "continue"


def test_rejects_empty_invalid_method_and_bad_counts():
    with pytest.raises(ValueError):
        metric_test.run_metric_tests([])
    with pytest.raises(ValueError):
        metric_test.run_metric_tests(_family(), method="holm")
    with pytest.raises(ValueError):
        metric_test.run_metric_tests([_metric(n1=0, c1=0)])
    with pytest.raises(ValueError):
        metric_test.run_metric_tests([_metric(n1=100, c1=200)])


def test_correction_helpers_monotone():
    ps = [0.001, 0.02, 0.2, 0.9]
    bh = metric_test.benjamini_hochberg(ps)
    bonf = metric_test.bonferroni(ps)
    assert all(0.0 <= q <= 1.0 for q in bh + bonf)
    assert bh == sorted(bh)  # 单调化后与 p 同序
    assert bonf == [min(1.0, p * 4) for p in ps]


def test_metric_tests_deterministic():
    first = metric_test.run_metric_tests(_family(), method="bh")
    second = metric_test.run_metric_tests(_family(), method="bh")
    assert first == second
