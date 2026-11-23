"""Small, dependency-free statistics used by several engines."""

from __future__ import annotations

import math


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def two_proportion_z(x1: int, n1: int, x2: int, n2: int) -> tuple[float | None, float | None]:
    """z statistic and two-sided p-value for H0: p1 == p2 (pooled). (None, None) if undefined."""
    if n1 == 0 or n2 == 0:
        return None, None
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (x1 / n1 - x2 / n2) / se
    return z, 2 * (1 - normal_cdf(abs(z)))


def one_sided_p(x_high: int, n_high: int, x_low: int, n_low: int) -> float | None:
    """p-value for H1: p_high > p_low."""
    z, _ = two_proportion_z(x_high, n_high, x_low, n_low)
    return None if z is None else 1 - normal_cdf(z)


def diff_ci(x1: int, n1: int, x2: int, n2: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wald 95% CI for p1 - p2 (unpooled)."""
    if n1 == 0 or n2 == 0:
        return None
    p1, p2 = x1 / n1, x2 / n2
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    d = p1 - p2
    return d - z * se, d + z * se


def wilson_ci(x: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = x / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def sample_size_confidence(n: int, k: int = 10) -> float:
    """Heuristic n / (n + k): 10 obs -> 0.5, 30 -> 0.75, 90 -> 0.9. Used where no test applies."""
    return round(n / (n + k), 3) if n > 0 else 0.0
