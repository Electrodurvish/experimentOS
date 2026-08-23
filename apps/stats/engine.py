"""
Pure statistical computation functions for experiment analysis.

All functions use only Python stdlib math — no scipy dependency.
Implements z-test for proportions, Wilson score CI, chi-squared SRM test,
relative lift with CI, and sample size estimation.
"""

import math


# ── Normal distribution helpers ──

def _norm_cdf(x):
    """Standard normal CDF using the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p):
    """
    Inverse standard normal CDF (percent point function).
    Rational approximation by Peter Acklam.
    Accurate to ~1.15e-9 for 0 < p < 1.
    """
    if p <= 0:
        return float("-inf")
    if p >= 1:
        return float("inf")

    # Coefficients for rational approximation
    a = [
        -3.969683028665376e+01,
        2.209460984245205e+02,
        -2.759285104469687e+02,
        1.383577518672690e+02,
        -3.066479806614716e+01,
        2.506628277459239e+00,
    ]
    b = [
        -5.447609879822406e+01,
        1.615858368580409e+02,
        -1.556989798598866e+02,
        6.680131188771972e+01,
        -1.328068155288572e+01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e+00,
        -2.549732539343734e+00,
        4.374664141464968e+00,
        2.938163982698783e+00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e+00,
        3.754408661907416e+00,
    ]

    p_low = 0.02425
    p_high = 1.0 - p_low

    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
               ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)
    elif p <= p_high:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5]) * q / \
               (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1.0)
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
                ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)


# ── Statistical functions ──

def wilson_confidence_interval(conversions, total, confidence=0.95):
    """
    Wilson score confidence interval for a binomial proportion.

    More accurate than the normal approximation, especially for small samples
    or extreme proportions.

    Returns (lower, upper) bounds.
    """
    if total <= 0:
        return (0.0, 0.0)

    z = _norm_ppf(1.0 - (1.0 - confidence) / 2.0)
    p_hat = conversions / total
    z2 = z * z

    denominator = 1.0 + z2 / total
    center = (p_hat + z2 / (2.0 * total)) / denominator
    margin = (z / denominator) * math.sqrt(
        (p_hat * (1.0 - p_hat) / total) + (z2 / (4.0 * total * total))
    )

    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)

    return (round(lower, 6), round(upper, 6))


def two_proportion_z_test(c1, n1, c2, n2):
    """
    Two-proportion z-test comparing two independent proportions.

    c1, n1: conversions and total for group 1 (control)
    c2, n2: conversions and total for group 2 (treatment)

    Returns (z_statistic, p_value) for a two-sided test.
    """
    if n1 <= 0 or n2 <= 0:
        return (0.0, 1.0)

    p1 = c1 / n1
    p2 = c2 / n2

    # Pooled proportion under H0
    p_pool = (c1 + c2) / (n1 + n2)

    se = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n1 + 1.0 / n2))

    if se == 0:
        return (0.0, 1.0)

    z = (p2 - p1) / se
    p_value = 2.0 * (1.0 - _norm_cdf(abs(z)))

    return (round(z, 4), round(p_value, 6))


def relative_lift(c_conv, c_total, t_conv, t_total, confidence=0.95):
    """
    Calculate relative lift of treatment over control with confidence interval.

    Uses the delta method for the CI on the ratio of proportions.

    Returns dict with lift, lift_ci_lower, lift_ci_upper, absolute_difference.
    """
    if c_total <= 0 or t_total <= 0:
        return {
            "lift": 0.0,
            "lift_ci_lower": 0.0,
            "lift_ci_upper": 0.0,
            "absolute_difference": 0.0,
        }

    p_c = c_conv / c_total
    p_t = t_conv / t_total

    if p_c == 0:
        return {
            "lift": 0.0 if p_t == 0 else float("inf"),
            "lift_ci_lower": 0.0,
            "lift_ci_upper": 0.0,
            "absolute_difference": round(p_t - p_c, 6),
        }

    lift = (p_t - p_c) / p_c
    absolute_diff = p_t - p_c

    # Delta method SE for ratio p_t / p_c
    var_t = p_t * (1.0 - p_t) / t_total
    var_c = p_c * (1.0 - p_c) / c_total

    # SE of (p_t / p_c) using delta method
    ratio = p_t / p_c
    se_ratio = ratio * math.sqrt(var_t / (p_t * p_t) + var_c / (p_c * p_c)) if p_t > 0 else 0.0

    z = _norm_ppf(1.0 - (1.0 - confidence) / 2.0)

    # CI on the ratio, then convert to lift (ratio - 1)
    lift_ci_lower = (ratio - z * se_ratio) - 1.0
    lift_ci_upper = (ratio + z * se_ratio) - 1.0

    return {
        "lift": round(lift, 6),
        "lift_ci_lower": round(lift_ci_lower, 6),
        "lift_ci_upper": round(lift_ci_upper, 6),
        "absolute_difference": round(absolute_diff, 6),
    }


def srm_test(observed_counts, expected_proportions=None):
    """
    Chi-squared goodness-of-fit test for Sample Ratio Mismatch detection.

    observed_counts: list of observed counts per variant [n1, n2, ...]
    expected_proportions: list of expected proportions [0.5, 0.5, ...].
        If None, assumes equal proportions.

    Returns (chi_squared_statistic, p_value).
    """
    k = len(observed_counts)
    if k < 2:
        return (0.0, 1.0)

    total = sum(observed_counts)
    if total <= 0:
        return (0.0, 1.0)

    if expected_proportions is None:
        expected_proportions = [1.0 / k] * k

    expected_counts = [p * total for p in expected_proportions]

    chi2 = 0.0
    for obs, exp in zip(observed_counts, expected_counts):
        if exp > 0:
            chi2 += (obs - exp) ** 2 / exp

    # Chi-squared CDF for df = k - 1
    p_value = 1.0 - _chi2_cdf(chi2, k - 1)

    return (round(chi2, 4), round(p_value, 6))


def _chi2_cdf(x, df):
    """
    Chi-squared CDF using the regularized lower incomplete gamma function.
    Uses series expansion for the incomplete gamma function.
    """
    if x <= 0:
        return 0.0
    return _regularized_gamma_p(df / 2.0, x / 2.0)


def _regularized_gamma_p(a, x):
    """
    Regularized lower incomplete gamma function P(a, x).
    Uses series expansion: P(a,x) = e^(-x) * x^a * sum(x^n / Gamma(a+n+1))
    """
    if x < 0:
        return 0.0
    if x == 0:
        return 0.0

    # Use series expansion for x < a + 1
    if x < a + 1:
        return _gamma_series(a, x)
    else:
        # Use continued fraction for x >= a + 1
        return 1.0 - _gamma_cf(a, x)


def _gamma_series(a, x, max_iter=200, eps=1e-12):
    """Series expansion for regularized incomplete gamma P(a, x)."""
    if x == 0:
        return 0.0

    ap = a
    sum_val = 1.0 / a
    delta = sum_val

    for _ in range(max_iter):
        ap += 1.0
        delta *= x / ap
        sum_val += delta
        if abs(delta) < abs(sum_val) * eps:
            break

    return sum_val * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_cf(a, x, max_iter=200, eps=1e-12):
    """Continued fraction for upper regularized incomplete gamma Q(a, x)."""
    b = x + 1.0 - a
    c = 1.0 / 1e-30
    d = 1.0 / b
    h = d

    for i in range(1, max_iter + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-30:
            d = 1e-30
        c = b + an / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break

    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def required_sample_size(baseline_rate, mde, alpha=0.05, power=0.80):
    """
    Required sample size per variant for a two-proportion z-test.

    baseline_rate: expected conversion rate of control
    mde: minimum detectable effect (absolute, e.g., 0.01 for 1%)
    alpha: significance level (default 0.05)
    power: statistical power (default 0.80)

    Returns required sample size per variant.
    """
    if baseline_rate <= 0 or baseline_rate >= 1 or mde <= 0:
        return 0

    p1 = baseline_rate
    p2 = baseline_rate + mde

    if p2 >= 1.0:
        p2 = 0.999

    z_alpha = _norm_ppf(1.0 - alpha / 2.0)
    z_beta = _norm_ppf(power)

    p_bar = (p1 + p2) / 2.0

    numerator = (z_alpha * math.sqrt(2.0 * p_bar * (1.0 - p_bar)) +
                 z_beta * math.sqrt(p1 * (1.0 - p1) + p2 * (1.0 - p2))) ** 2
    denominator = (p2 - p1) ** 2

    return math.ceil(numerator / denominator)


def is_significant(p_value, alpha=0.05):
    """Check if a p-value indicates statistical significance."""
    return p_value < alpha
