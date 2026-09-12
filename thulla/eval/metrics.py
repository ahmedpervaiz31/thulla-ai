"""Eval metrics for Thulla bots."""

import math


def brier_score(pairs):
    """pairs: iterable of (p_hat, y) with y in {0,1}."""
    pairs = list(pairs)
    if not pairs:
        return 0.0
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def reliability_bins(pairs, bin_width=0.1):
    """
    Return list of dicts: {lo, hi, center, count, emp_freq, mean_p}.
    Empty bins omitted.
    """
    pairs = list(pairs)
    n_bins = int(round(1.0 / bin_width))
    buckets = [[] for _ in range(n_bins)]
    for p, y in pairs:
        idx = min(n_bins - 1, max(0, int(p / bin_width)))
        buckets[idx].append((p, y))

    rows = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        lo = i * bin_width
        hi = (i + 1) * bin_width
        mean_p = sum(p for p, _ in bucket) / len(bucket)
        emp = sum(y for _, y in bucket) / len(bucket)
        rows.append(
            {
                "lo": lo,
                "hi": hi,
                "center": (lo + hi) / 2,
                "count": len(bucket),
                "emp_freq": emp,
                "mean_p": mean_p,
            }
        )
    return rows


def lose_rate_ci(losses, n, z=1.96):
    """Agresti-Coull approximate 95% CI for a proportion."""
    if n <= 0:
        return 0.0, 0.0, 0.0
    p = losses / n
    n2 = n + z * z
    p2 = (losses + z * z / 2) / n2
    se = math.sqrt(p2 * (1 - p2) / n2)
    return p, max(0.0, p2 - z * se), min(1.0, p2 + z * se)


def format_reliability_table(rows):
    lines = ["bin           n    mean_p  emp_freq"]
    for r in rows:
        lines.append(
            f"[{r['lo']:.1f},{r['hi']:.1f})  {r['count']:5d}  "
            f"{r['mean_p']:.3f}   {r['emp_freq']:.3f}"
        )
    return "\n".join(lines)
