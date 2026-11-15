"""算法 B：双比例 z 检验 + 多重比较校正（Bonferroni / BH-FDR）。

输入 metrics（每个指标一条，含对照与实验组的样本量/转化数）：
  {"metric_key","metric_name","is_primary",
   "control": {"n","conversions"}, "variant": {"code","name","n","conversions"}}
校验口径：
  p1 = 实验组转化率, p2 = 对照组转化率
  z  = (p1-p2)/sqrt(p_pool(1-p_pool)(1/n1+1/n2))，双侧 p = 2(1-Φ(|z|))
  CI = (p1-p2) ± z_{1-α/2}·sqrt(p1(1-p1)/n1 + p2(1-p2)/n2)     （Wald）
  lift = (p1-p2)/p2，lift CI 由同一区间除以 p2 得到
  Bonferroni: q = min(1, m·p)；BH-FDR: 升序 q_i = min_{k>=i}(m·p_k/k)，再单调化
  q < 0.05 才算显著；结论 ship / stop / continue
"""
from __future__ import annotations

from src.constants.limits import DEFAULT_ALPHA, DEFAULT_POWER
from src.services.algorithms import stats


def _rate(conversions: int, n: int) -> float:
    return conversions / n if n > 0 else 0.0


def bonferroni(p_values: list[float]) -> list[float]:
    m = len(p_values)
    if m == 0:
        return []
    return [min(1.0, value * m) for value in p_values]


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda index: (p_values[index], index))
    adjusted = [1.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        index = order[rank - 1]
        candidate = p_values[index] * m / rank
        running = min(running, candidate)
        adjusted[index] = min(1.0, running)
    return adjusted


def verdict_of(significant: bool, diff: float) -> str:
    if significant and diff > 0:
        return "ship"
    if significant and diff < 0:
        return "stop"
    return "continue"


def run_metric_tests(
    metrics: list[dict],
    *,
    method: str = "bh",
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
) -> dict:
    if not metrics:
        raise ValueError("没有可检验的指标")
    if method not in ("bh", "bonferroni"):
        raise ValueError("method 只支持 bh / bonferroni")

    items: list[dict] = []
    p_values: list[float] = []
    for metric in metrics:
        control = metric.get("control") or {}
        variant = metric.get("variant") or {}
        n2 = int(control.get("n") or 0)
        c2 = int(control.get("conversions") or 0)
        n1 = int(variant.get("n") or 0)
        c1 = int(variant.get("conversions") or 0)
        if n1 <= 0 or n2 <= 0:
            raise ValueError("对照与实验组样本量都必须大于 0")
        if not (0 <= c1 <= n1 and 0 <= c2 <= n2):
            raise ValueError("转化数必须落在 [0, n] 区间内")
        p1 = _rate(c1, n1)
        p2 = _rate(c2, n2)
        pooled = (c1 + c2) / (n1 + n2)
        variance = pooled * (1.0 - pooled) * (1.0 / n1 + 1.0 / n2)
        z = (p1 - p2) / variance**0.5 if variance > 0 else 0.0
        p_value = 2.0 * stats.norm_sf(abs(z)) if variance > 0 else 1.0
        diff = p1 - p2
        se_unpooled = (p1 * (1.0 - p1) / n1 + p2 * (1.0 - p2) / n2) ** 0.5
        z_crit = stats.norm_ppf(1.0 - alpha / 2.0)
        ci_low = diff - z_crit * se_unpooled
        ci_high = diff + z_crit * se_unpooled
        lift = diff / p2 if p2 > 0 else 0.0
        lift_ci_low = ci_low / p2 if p2 > 0 else 0.0
        lift_ci_high = ci_high / p2 if p2 > 0 else 0.0
        required = (
            stats.required_sample_per_variant(p2, abs(diff), alpha, power) if diff != 0 and 0 < p2 < 1 else 0
        )
        achieved = stats.achieved_power(min(n1, n2), p2, abs(diff), alpha) if diff != 0 and 0 < p2 < 1 else 0.0
        p_values.append(p_value)
        items.append(
            {
                "metric_key": metric.get("metric_key") or "",
                "metric_name": metric.get("metric_name") or metric.get("metric_key") or "",
                "is_primary": bool(metric.get("is_primary")),
                "variant_code": variant.get("code") or "",
                "variant_name": variant.get("name") or "",
                "control_n": n2,
                "control_conversions": c2,
                "variant_n": n1,
                "variant_conversions": c1,
                "control_rate": stats.round_half_up(p2, 6),
                "variant_rate": stats.round_half_up(p1, 6),
                "pooled_rate": stats.round_half_up(pooled, 6),
                "diff": stats.round_half_up(diff, 6),
                "z": stats.round_half_up(z, 4),
                "p_value": p_value,
                "ci_low": stats.round_half_up(ci_low, 6),
                "ci_high": stats.round_half_up(ci_high, 6),
                "lift": stats.round_half_up(lift, 6),
                "lift_ci_low": stats.round_half_up(lift_ci_low, 6),
                "lift_ci_high": stats.round_half_up(lift_ci_high, 6),
                "required_n": int(required),
                "power_at_current": stats.round_half_up(achieved, 4),
                "alpha": alpha,
            }
        )

    q_bh = benjamini_hochberg(p_values)
    q_bonf = bonferroni(p_values)
    m = len(items)
    for index, item in enumerate(items):
        q_applied = q_bh[index] if method == "bh" else q_bonf[index]
        item["q_bh"] = stats.round_half_up(q_bh[index], 6)
        item["q_bonferroni"] = stats.round_half_up(q_bonf[index], 6)
        item["q_value"] = stats.round_half_up(q_applied, 6)
        item["significant"] = q_applied < alpha
        item["verdict"] = verdict_of(item["significant"], item["diff"])
        item["verdict_label"] = {"ship": "上线", "stop": "停止", "continue": "继续观察"}[item["verdict"]]

    primary = next((item for item in items if item["is_primary"]), None)
    significant_count = sum(1 for item in items if item["significant"])
    experiment_verdict = primary["verdict"] if primary else "continue"
    return {
        "method": method,
        "alpha": alpha,
        "metrics_count": m,
        "significant_count": significant_count,
        "items": items,
        "primary": primary,
        "experiment_verdict": experiment_verdict,
        "experiment_verdict_label": {"ship": "上线", "stop": "停止", "continue": "继续观察"}[experiment_verdict],
        "note": (
            f"{m} 个指标同时看，{method.upper()} 校正后 {significant_count} 个显著；"
            f"主指标 {primary['metric_name'] if primary else '—'} q={primary['q_value'] if primary else '—'}"
        ),
    }
