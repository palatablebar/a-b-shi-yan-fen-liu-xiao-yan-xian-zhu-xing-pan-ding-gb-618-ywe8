"""算法 A：分流均衡（SRM）χ² 检验 + 样本量/功效缺口。

输入（纯数据，不碰数据库）：
  variants: [{"code","name","ratio","observed","is_control"}, ...]
  baseline_rate: 主指标对照组基准转化率 p
  planned_mde:  计划检测的最小绝对提升 Δ
输出：
  chi2 = Σ (obs-exp)²/exp, df = k-1, p = 卡方上尾概率
  cells[]: 每个变体的期望/实测/占比/单元贡献（单格贡献 = (obs-exp)²/exp）
  required_per_variant: n = 2(z_{1-α/2}+z_{1-β})² p(1-p)/Δ²
  gap_per_variant: max(0, n_required - n_observed)
  power_at_current: 以当前最小变体样本量对 Δ 的功效
  mde_at_current:   以当前最小变体样本量能检测的最小效应
全部只依赖 math，同样输入两次结果逐位一致。
"""
from __future__ import annotations

from src.constants.limits import DEFAULT_ALPHA, DEFAULT_POWER, SRM_ALARM_P
from src.services.algorithms import stats


def run_srm(
    variants: list[dict],
    *,
    baseline_rate: float = 0.1,
    planned_mde: float = 0.01,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    alarm_p: float = SRM_ALARM_P,
) -> dict:
    cells_in = [row for row in variants if isinstance(row, dict)]
    if len(cells_in) < 2:
        raise ValueError("SRM 检验至少需要 2 个变体")
    observed = [int(row.get("observed") or 0) for row in cells_in]
    if any(value < 0 for value in observed):
        raise ValueError("分流样本数不能为负")
    total = sum(observed)
    if total <= 0:
        raise ValueError("分流样本合计为 0，无法做 SRM 检验")

    ratios = [float(row.get("ratio") or 0.0) for row in cells_in]
    ratio_sum = sum(ratios)
    if ratio_sum <= 0:
        raise ValueError("计划分流比例合计必须为正")
    # 计划比例归一化（允许录入 34/33/33 这样的整数比例）
    ratios = [value / ratio_sum for value in ratios]

    chi2 = 0.0
    cells = []
    for row, count, ratio in zip(cells_in, observed, ratios):
        expected = total * ratio
        diff = count - expected
        contribution = (diff * diff) / expected if expected > 0 else 0.0
        chi2 += contribution
        cells.append(
            {
                "code": row.get("code") or "",
                "name": row.get("name") or row.get("code") or "",
                "is_control": bool(row.get("is_control")),
                "ratio": stats.round_half_up(ratio, 6),
                "ratio_pct": stats.round_half_up(ratio * 100, 4),
                "observed": count,
                "expected": stats.round_half_up(expected, 2),
                "diff": count - int(round(expected)),
                "share_pct": stats.round_half_up(count / total * 100, 4),
                "contribution": stats.round_half_up(contribution, 4),
            }
        )

    df = len(cells_in) - 1
    p_value = stats.chi2_sf(chi2, df)
    alarm = p_value < alarm_p

    required = stats.required_sample_per_variant(baseline_rate, planned_mde, alpha, power)
    min_observed = min(observed)
    gaps = [max(0, required - count) for count in observed]
    power_current = stats.achieved_power(min_observed, baseline_rate, planned_mde, alpha)
    mde_current = stats.minimal_detectable_effect(min_observed, baseline_rate, alpha, power)

    for cell, gap in zip(cells, gaps):
        cell["required"] = required
        cell["gap"] = gap

    return {
        "total": total,
        "chi2": stats.round_half_up(chi2, 4),
        "df": df,
        "p_value": p_value,
        "p_value_fmt": f"{p_value:.6f}" if p_value >= 1e-4 else f"{p_value:.2e}",
        "alarm_threshold": alarm_p,
        "status": "srm" if alarm else "balanced",
        "alarm": alarm,
        "cells": cells,
        "baseline_rate": stats.round_half_up(baseline_rate, 6),
        "planned_mde": stats.round_half_up(planned_mde, 6),
        "alpha": alpha,
        "power_target": power,
        "required_per_variant": required,
        "gap_total": sum(gaps),
        "gap_per_variant": gaps,
        "power_at_current": stats.round_half_up(power_current, 4),
        "mde_at_current": stats.round_half_up(mde_current, 6),
        "min_observed": min_observed,
        "note": (
            f"χ²={chi2:.2f} (df={df})，p={p_value:.6f} < {alarm_p}，分流显著不均，先修分流再谈指标"
            if alarm
            else f"χ²={chi2:.2f} (df={df})，p={p_value:.4f} ≥ {alarm_p}，分流未见系统性偏差"
        ),
    }
