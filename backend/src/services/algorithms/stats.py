"""统计学底座：只用标准库 math 实现，纯函数、确定性。

包含：
- 标准正态 CDF / 分位数（Acklam 有理逼近 + 一步 Halley 精修）
- 卡方分布上尾概率 = 正则化上不完全伽马 Q(df/2, x/2)
  （级数展开 + Lentz 连分式，Numerical Recipes gammp/gammq）
- 样本量 / 功效 / 最小可检测效应（MDE）
两个业务算法（srm.py、metric_test.py）都只依赖这里，不做任何 IO。
"""
from __future__ import annotations

import math

_EPS = 3e-16
_FPMIN = 1e-300
_MAX_ITER = 500


# ---------------------------------------------------------------- 正态分布
def norm_cdf(z: float) -> float:
    """标准正态分布函数 Φ(z)。"""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def norm_sf(z: float) -> float:
    """上尾概率 1 - Φ(z)，大 z 时避免相减抵消。"""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)
_P_LOW = 0.02425
_P_HIGH = 1.0 - _P_LOW


def norm_ppf(p: float) -> float:
    """标准正态分位数，Acklam 逼近 + Halley 精修（|误差| < 1e-15）。"""
    if not 0.0 < p < 1.0:
        raise ValueError("p 必须在 (0, 1) 之间")
    if p < _P_LOW:
        q = math.sqrt(-2.0 * math.log(p))
        x = (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    elif p <= _P_HIGH:
        q = p - 0.5
        r = q * q
        x = (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q / (
            ((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0
        )
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        x = -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    # Halley 精修一步
    e = norm_cdf(x) - p
    u = e * math.sqrt(2.0 * math.pi) * math.exp(x * x / 2.0)
    return x - u / (1.0 + x * u / 2.0)


# ---------------------------------------------------------------- 伽马 / 卡方
def _gamma_prefactor(s: float, x: float) -> float:
    return math.exp(-x + s * math.log(x) - math.lgamma(s))


def _gamma_series(s: float, x: float) -> float:
    """正则化下不完全伽马 P(s, x)，x < s+1 时收敛快。"""
    ap = s
    term = 1.0 / s
    total = term
    for _ in range(_MAX_ITER):
        ap += 1.0
        term *= x / ap
        total += term
        if abs(term) < abs(total) * _EPS:
            break
    return total * _gamma_prefactor(s, x)


def _gamma_cf(s: float, x: float) -> float:
    """正则化上不完全伽马 Q(s, x)，Lentz 连分式，x >= s+1 时收敛快。"""
    b = x + 1.0 - s
    c = 1.0 / _FPMIN
    d = 1.0 / b
    h = d
    for i in range(1, _MAX_ITER):
        an = -i * (i - s)
        b += 2.0
        d = an * d + b
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = b + an / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return _gamma_prefactor(s, x) * h


def gammainc_q(s: float, x: float) -> float:
    """正则化上不完全伽马 Q(s, x) = 1 - P(s, x)。"""
    if x <= 0.0:
        return 1.0
    if x < s + 1.0:
        return max(0.0, 1.0 - _gamma_series(s, x))
    return min(1.0, _gamma_cf(s, x))


def chi2_sf(chi2: float, df: int) -> float:
    """卡方分布上尾概率 P(X² >= chi2)，即 SRM 的 p 值。"""
    if df <= 0:
        raise ValueError("df 必须为正整数")
    if chi2 <= 0.0:
        return 1.0
    return gammainc_q(df / 2.0, chi2 / 2.0)


# ---------------------------------------------------------------- 样本量 / 功效
def required_sample_per_variant(
    baseline: float,
    mde_abs: float,
    alpha: float = 0.05,
    power: float = 0.8,
) -> int:
    """每个变体所需样本量 n = 2(z_{1-α/2}+z_{1-β})²·p(1-p)/Δ²。

    baseline 为对照基准转化率 p，mde_abs 为最小可检测的绝对提升 Δ（>0）。
    """
    if not 0.0 < baseline < 1.0:
        raise ValueError("baseline 必须在 (0, 1) 之间")
    if mde_abs <= 0.0:
        raise ValueError("mde_abs 必须为正")
    if not 0.0 < alpha < 1.0 or not 0.0 < power < 1.0:
        raise ValueError("alpha / power 必须在 (0, 1) 之间")
    z_alpha = norm_ppf(1.0 - alpha / 2.0)
    z_beta = norm_ppf(power)
    n = 2.0 * (z_alpha + z_beta) ** 2 * baseline * (1.0 - baseline) / (mde_abs**2)
    return int(math.ceil(n))


def achieved_power(
    n_per_variant: int,
    baseline: float,
    mde_abs: float,
    alpha: float = 0.05,
) -> float:
    """给定每变体样本量 n，对效应 Δ 的功效 = Φ(√(nΔ²/(2p(1-p))) - z_{1-α/2})。"""
    if n_per_variant <= 0:
        return 0.0
    if not 0.0 < baseline < 1.0:
        raise ValueError("baseline 必须在 (0, 1) 之间")
    if mde_abs <= 0.0:
        return 0.0
    z_alpha = norm_ppf(1.0 - alpha / 2.0)
    ncp = math.sqrt(n_per_variant * mde_abs**2 / (2.0 * baseline * (1.0 - baseline)))
    return norm_cdf(ncp - z_alpha)


def minimal_detectable_effect(
    n_per_variant: int,
    baseline: float,
    alpha: float = 0.05,
    power: float = 0.8,
) -> float:
    """反解：当前样本量能检测出的最小绝对效应 Δ。"""
    if n_per_variant <= 0:
        raise ValueError("n 必须为正")
    z_alpha = norm_ppf(1.0 - alpha / 2.0)
    z_beta = norm_ppf(power)
    return (z_alpha + z_beta) * math.sqrt(2.0 * baseline * (1.0 - baseline) / n_per_variant)


def round_half_up(value: float, digits: int = 6) -> float:
    """统一四舍五入，保证两次计算逐位一致（避免 -0.0）。"""
    if value == 0:
        return 0.0
    return float(f"{value:.{digits}f}")
