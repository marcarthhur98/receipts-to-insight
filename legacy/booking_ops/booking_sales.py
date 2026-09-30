"""booking_sales.py — sales & service-mix analysis (deterministic).

Answers, per service:
  - revenue and revenue share
  - revenue per chair-hour (the profitability PROXY when only price is known;
    optional cost inputs turn this into true margin)
  - a transparent growth-potential score
  - reliability (no-show / cancellation), support-gated

We never call price-only output "profit". Chair-time is the salon's scarce
resource, so revenue ÷ booked hours is the honest stand-in for profitability.
"""
import pandas as pd
from booking_kpis import MIN_SUPPORT

from booking_config import GROWTH_W_TREND as W_TREND, GROWTH_W_YIELD as W_YIELD, GROWTH_W_RELIAB as W_RELIAB


def _completed_priced(df):
    c = df[df["status"] == "completed"].copy()
    if "price" in c:
        c = c[c["price"].notna()]
    return c


def _svc_reliability(df):
    """No-show + cancellation rate per service over the whole window (gated)."""
    res = df[df["status"].isin(["completed", "cancelled", "no_show"])]
    out = {}
    for svc, g in res.groupby("service"):
        n = len(g)
        out[svc] = {
            "no_show_rate": round(float((g["status"] == "no_show").mean()) * 100, 1),
            "cancel_rate": round(float((g["status"] == "cancelled").mean()) * 100, 1),
            "n": int(n), "confident": n >= MIN_SUPPORT,
        }
    return out


def _service_trend(df):
    """Revenue change per service: recent half vs prior half (% change)."""
    c = _completed_priced(df).dropna(subset=["date"])
    if c["date"].nunique() < 4:
        return {}
    lo, hi = c["date"].min(), c["date"].max()
    cutoff = lo + (hi - lo) / 2
    prior, recent = c[c["date"] <= cutoff], c[c["date"] > cutoff]
    pr = prior.groupby("service")["price"].sum()
    rc = recent.groupby("service")["price"].sum()
    out = {}
    for svc in set(pr.index) | set(rc.index):
        p, r = float(pr.get(svc, 0)), float(rc.get(svc, 0))
        pct = ((r - p) / p * 100) if p > 0 else (100.0 if r > 0 else 0.0)
        out[svc] = round(pct, 1)
    return out


def prime_time_yield(df):
    """Is peak time filled with high-yield services? Compares revenue-per-hour in
    the busiest (weekday, hour) cells against the overall average, and suggests a
    high-yield service to push into peak and a low-yield one to move off-peak."""
    comp = df[df["status"] == "completed"].dropna(subset=["hour", "duration_min", "date"]).copy()
    if "price" in comp:
        comp = comp[comp["price"].notna()]
    if comp.empty or "service" not in comp.columns:
        return None
    comp["hours"] = comp["duration_min"] / 60
    comp["weekday"] = comp["date"].dt.day_name()
    cell = comp.groupby(["weekday", "hour"]).size()
    if cell.empty:
        return None
    prime_idx = set(cell[cell >= cell.quantile(0.75)].index)
    comp["prime"] = [(w, h) in prime_idx for w, h in zip(comp["weekday"], comp["hour"])]

    def yld(g):
        hh = g["hours"].sum()
        return float(g["price"].sum()) / hh if hh else 0.0

    prime = comp[comp["prime"]]
    if prime.empty:
        return None
    rev = comp.groupby("service")["price"].sum()
    hrs = comp.groupby("service")["hours"].sum().replace(0, 1)
    svc_yield = rev / hrs
    med = float(svc_yield.median())
    prime_hours = prime.groupby("service")["hours"].sum()
    low = [s for s in prime_hours.sort_values(ascending=False).index if svc_yield.get(s, 0) < med]
    move = low[0] if low else None
    promote = None
    for s in svc_yield.sort_values(ascending=False).index:
        if prime_hours.get(s, 0) < prime_hours.median():
            promote = s
            break
    return {"prime_yield": round(yld(prime), 2), "overall_yield": round(yld(comp), 2),
            "gap": round(yld(comp) - yld(prime), 2), "move": move, "promote": promote}


def compute_sales(df, cost_inputs=None):
    """Full per-service sales analysis + rankings. cost_inputs is an optional
    dict: {service: {"commission_pct": x, "product_cost": y}, "_default": {...}}."""
    if "service" not in df.columns or "price" not in df.columns:
        return {"total_revenue": 0.0, "by_service": {}, "rankings": {},
                "has_costs": bool(cost_inputs), "price_coverage": 0.0, "prime_time": None}
    completed = _completed_priced(df)
    total_rev = float(completed["price"].sum()) if len(completed) else 0.0
    reliability = _svc_reliability(df)
    trend = _service_trend(df)

    by_service = {}
    for svc, g in completed.groupby("service"):
        bookings = len(g)
        revenue = float(g["price"].sum())
        hours = float(g["duration_min"].sum()) / 60 if "duration_min" in g else 0.0
        yph = round(revenue / hours, 2) if hours else 0.0
        rec = {
            "bookings": bookings,
            "revenue": round(revenue, 2),
            "revenue_share": round(revenue / total_rev * 100, 1) if total_rev else 0.0,
            "avg_price": round(revenue / bookings, 2) if bookings else 0.0,
            "hours": round(hours, 1),
            "revenue_per_hour": yph,
            "no_show_rate": reliability.get(svc, {}).get("no_show_rate", 0.0),
            "cancel_rate": reliability.get(svc, {}).get("cancel_rate", 0.0),
            "revenue_trend_pct": trend.get(svc, 0.0),
            "confident": bookings >= MIN_SUPPORT,
        }
        if cost_inputs:
            ci = cost_inputs.get(svc, cost_inputs.get("_default", {}))
            comm = ci.get("commission_pct", 0) / 100.0
            prod = ci.get("product_cost", 0)
            margin = revenue * (1 - comm) - prod * bookings
            rec["margin"] = round(margin, 2)
            rec["margin_per_hour"] = round(margin / hours, 2) if hours else 0.0
        by_service[svc] = rec

    # --- growth-potential score (transparent, supported services only) ---
    supported = {s: r for s, r in by_service.items() if r["confident"]}
    if supported:
        max_yph = max(r["revenue_per_hour"] for r in supported.values()) or 1
        for svc, r in supported.items():
            trend_norm = max(0.0, min((r["revenue_trend_pct"] + 25) / 50, 1.0))   # -25%..+25% -> 0..1
            yield_norm = r["revenue_per_hour"] / max_yph
            reliab_norm = max(0.0, 1 - (r["no_show_rate"] + r["cancel_rate"]) / 40)  # 0..40% bad -> 1..0
            score = round(W_TREND * trend_norm + W_YIELD * yield_norm + W_RELIAB * reliab_norm, 3)
            by_service[svc]["growth_score"] = score
            by_service[svc]["growth_parts"] = {"trend": round(trend_norm, 2),
                                               "yield": round(yield_norm, 2),
                                               "reliability": round(reliab_norm, 2)}

    def _rank(metric, supported_only=True, lowest=False):
        pool = supported if supported_only else by_service
        pool = {s: r for s, r in pool.items() if metric in r}
        if not pool:
            return None
        return (min if lowest else max)(pool, key=lambda s: pool[s][metric])

    rankings = {
        "top_revenue": _rank("revenue", supported_only=False),
        "top_yield": _rank("revenue_per_hour"),
        "fastest_growth": _rank("revenue_trend_pct"),
        "lowest_noshow": _rank("no_show_rate", lowest=True),
        "best_growth_potential": _rank("growth_score"),
    }
    return {"total_revenue": round(total_rev, 2), "by_service": by_service,
            "rankings": rankings, "has_costs": bool(cost_inputs), "prime_time": prime_time_yield(df),
            "price_coverage": round(len(completed) / max((df["status"] == "completed").sum(), 1) * 100, 1)}
