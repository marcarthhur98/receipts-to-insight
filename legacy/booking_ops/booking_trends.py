"""booking_trends.py — longitudinal revenue & leakage analysis (vertical-neutral).

Answers the spine question — "is the business growing, and where is revenue/time
leaking, over time" — by reading the deepened history store:
  - which SERVICES drove the latest revenue change (and price vs volume),
  - whether a PROVIDER's book is declining (auto, only if staff history exists),
  - the leakage (no-show) trend.

Everything is gated on having at least two periods of history; with less, it
returns None rather than inventing a trend. Language is neutral (service,
provider, booked hours) so it fits any appointment-based business.
"""
from booking_history import monthly_history, monthly_by
from booking_config import TREND_MIN_DELTA


def _months(monthly_df):
    return list(monthly_df.sort_values("month")["month"].unique())


def revenue_drivers(service_history):
    """Top services that raised or lowered revenue, latest month vs the prior."""
    if service_history is None or len(service_history) == 0:
        return None
    ms = monthly_by(service_history, "service")
    months = _months(ms)
    if len(months) < 2:
        return None
    prevm, lastm = months[-2], months[-1]
    prev = ms[ms["month"] == prevm].set_index("service")["revenue"]
    last = ms[ms["month"] == lastm].set_index("service")["revenue"]
    deltas = {s: round(float(last.get(s, 0)) - float(prev.get(s, 0)), 0)
              for s in set(prev.index) | set(last.index)}
    up = [(s, d) for s, d in sorted(deltas.items(), key=lambda x: -x[1]) if d >= TREND_MIN_DELTA][:3]
    down = [(s, d) for s, d in sorted(deltas.items(), key=lambda x: x[1]) if d <= -TREND_MIN_DELTA][:3]
    return {"prev_label": ms[ms.month == prevm]["month_label"].iloc[0],
            "last_label": ms[ms.month == lastm]["month_label"].iloc[0],
            "up": up, "down": down}


def price_volume_split(weekly_history):
    """Decompose the latest month's revenue change into volume vs price effects."""
    m = monthly_history(weekly_history)
    if len(m) < 2:
        return None
    prev, last = m.iloc[-2], m.iloc[-1]
    rev_change = round(float(last["revenue"] - prev["revenue"]), 0)
    volume_effect = round(float((last["completed"] - prev["completed"]) * prev["avg_ticket"]), 0)
    price_effect = round(float((last["avg_ticket"] - prev["avg_ticket"]) * last["completed"]), 0)
    driver = "volume" if abs(volume_effect) >= abs(price_effect) else "price"
    return {"prev_label": prev["month_label"], "last_label": last["month_label"],
            "rev_change": rev_change, "volume_effect": volume_effect,
            "price_effect": price_effect, "driver": driver}


def provider_watch(staff_history):
    """The provider whose revenue fell most, latest month vs prior (material only)."""
    if staff_history is None or len(staff_history) == 0:
        return None
    ms = monthly_by(staff_history, "staff")
    months = _months(ms)
    if len(months) < 2:
        return None
    prevm, lastm = months[-2], months[-1]
    prev = ms[ms["month"] == prevm].set_index("staff")["revenue"]
    last = ms[ms["month"] == lastm].set_index("staff")["revenue"]
    worst, worst_d = None, -TREND_MIN_DELTA
    for s in set(prev.index) & set(last.index):
        d = float(last[s]) - float(prev[s])
        if d < worst_d:
            worst, worst_d = s, d
    if worst is None:
        return None
    return {"staff": worst, "delta": round(worst_d, 0),
            "prev_rev": round(float(prev[worst]), 0), "last_rev": round(float(last[worst]), 0),
            "prev_label": ms[ms.month == prevm]["month_label"].iloc[0],
            "last_label": ms[ms.month == lastm]["month_label"].iloc[0]}


def leakage_trend(weekly_history):
    """No-show rate, latest month vs prior."""
    m = monthly_history(weekly_history)
    if len(m) < 2:
        return None
    prev, last = m.iloc[-2], m.iloc[-1]
    return {"prev_label": prev["month_label"], "last_label": last["month_label"],
            "prev": round(float(prev["no_show_rate"]), 1), "last": round(float(last["no_show_rate"]), 1),
            "delta": round(float(last["no_show_rate"] - prev["no_show_rate"]), 1)}


def compute_trends(weekly_history, service_history, staff_history):
    return {"price_volume": price_volume_split(weekly_history),
            "drivers": revenue_drivers(service_history),
            "provider_watch": provider_watch(staff_history),
            "leakage": leakage_trend(weekly_history)}
