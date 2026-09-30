"""revenue_trends.py — descriptive growth analysis (no recommendations).

Answers "how is the business growing, and what changed" from the monthly history
and the current receipts — month-over-month growth, best/worst months, a
price-vs-volume read on the latest change, and which services moved the needle.
Purely descriptive; gated on having at least two months of data.
"""
import pandas as pd

TREND_MIN_DELTA = 100.0  # smallest revenue move ($) worth naming as a driver
# A month counts as "flat" when its revenue change is below the larger of a fixed
# floor and a share of the prior month — so the test scales with business size.
FLAT_THRESHOLD = 50.0      # fixed floor ($)
FLAT_THRESHOLD_PCT = 0.01  # ...or 1% of the prior month's revenue, whichever is bigger

def _month_label(month):
    """'2025-05' -> 'May 2025'."""
    return pd.to_datetime(month + "-01").strftime("%b %Y")


def growth_summary(history):
    if history is None or len(history) < 2:
        return None
    last, prev = history.iloc[-1], history.iloc[-2]
    rev_change = round(float(last["revenue"] - prev["revenue"]), 0)
    pct = round((last["revenue"] - prev["revenue"]) / prev["revenue"] * 100, 1) if prev["revenue"] else 0.0
    best = history.loc[history["revenue"].idxmax()]
    worst = history.loc[history["revenue"].idxmin()]
    return {"last_label": last["month_label"], "prev_label": prev["month_label"],
            "last_revenue": round(float(last["revenue"]), 0), "rev_change": rev_change, "pct": pct,
            "best_label": best["month_label"], "best_revenue": round(float(best["revenue"]), 0),
            "worst_label": worst["month_label"], "worst_revenue": round(float(worst["revenue"]), 0),
            "months_tracked": int(len(history))}


def price_volume(history):
    """Split the latest month's change into volume (more/fewer sales) vs price
    (higher/lower average sale)."""
    if history is None or len(history) < 2:
        return None
    last, prev = history.iloc[-1], history.iloc[-2]
    avg_prev = prev["revenue"] / prev["sales"] if prev["sales"] else 0
    avg_last = last["revenue"] / last["sales"] if last["sales"] else 0
    volume_effect = round(float((last["sales"] - prev["sales"]) * avg_prev), 0)
    price_effect = round(float((avg_last - avg_prev) * last["sales"]), 0)
    total_change = float(last["revenue"] - prev["revenue"])
    flat_cutoff = max(FLAT_THRESHOLD, FLAT_THRESHOLD_PCT * float(prev["revenue"]))
    if abs(total_change) < flat_cutoff:
        driver = "flat"
    elif abs(volume_effect) >= abs(price_effect):
        driver = "volume"
    else:
        driver = "price"
    return {"volume_effect": volume_effect, "price_effect": price_effect,
            "total_change": round(total_change, 0), "driver": driver,
            "last_label": last["month_label"], "prev_label": prev["month_label"]}

def category_drivers(df):
    """Which services rose/fell most in revenue, latest month vs prior, from the
    current file. Returns None if there's no category column or <2 months."""
    FLAT_THRESHOLD = 50.0
    if "category" not in df.columns or "month" not in df.columns:
        return None
    months = sorted(df["month"].unique())
    if len(months) < 2:
        return None
    prevm, lastm = months[-2], months[-1]
    prev = df[df["month"] == prevm].groupby("category")["amount"].sum()
    last = df[df["month"] == lastm].groupby("category")["amount"].sum()
    deltas = {c: round(float(last.get(c, 0)) - float(prev.get(c, 0)), 0)
              for c in set(prev.index) | set(last.index)}
    up = [(c, d) for c, d in sorted(deltas.items(), key=lambda x: -x[1]) if d >= TREND_MIN_DELTA][:3]
    down = [(c, d) for c, d in sorted(deltas.items(), key=lambda x: x[1]) if d <= -TREND_MIN_DELTA][:3]
    return {"prev_label": _month_label(prevm), "last_label": _month_label(lastm), "up": up, "down": down}
    

# ---------------- the yearly perspective ----------------
def _pct(curr, prev):
    """Percent change, or None when there's no comparable prior figure."""
    return round((curr - prev) / prev * 100, 1) if prev else None


def annual_summary(history):
    """One row per calendar year: revenue, sales, average sale, months of data,
    and year-over-year growth vs the previous year. Sorted oldest → newest."""
    if history is None or len(history) == 0:
        return []
    h = history.copy()
    h["year"] = h["month"].str[:4]
    rows = []
    for year, g in h.groupby("year"):
        rev = float(g["revenue"].sum()); n = int(g["sales"].sum())
        rows.append({"year": year, "revenue": round(rev, 0), "sales": n,
                     "avg_sale": round(rev / n, 2) if n else 0.0, "months": int(len(g))})
    rows.sort(key=lambda r: r["year"])
    for i, r in enumerate(rows):
        r["yoy_pct"] = _pct(r["revenue"], rows[i - 1]["revenue"]) if i else None
    return rows


def same_month_last_year(history):
    """Compare the latest month to the same calendar month a year earlier — the
    seasonality-aware read on real growth. None if that month isn't on record."""
    if history is None or len(history) < 13:
        return None
    last = history.iloc[-1]
    ym, mm = last["month"].split("-")
    prior_key = f"{int(ym) - 1}-{mm}"
    match = history[history["month"] == prior_key]
    if match.empty:
        return None
    prior = match.iloc[0]
    return {"label": last["month_label"], "revenue": round(float(last["revenue"]), 0),
            "prior_label": prior["month_label"], "prior_revenue": round(float(prior["revenue"]), 0),
            "pct": _pct(float(last["revenue"]), float(prior["revenue"]))}


def trailing_12(history):
    """Revenue and sales over the most recent (up to) 12 months on record."""
    if history is None or len(history) == 0:
        return None
    window = history.tail(12)
    return {"revenue": round(float(window["revenue"].sum()), 0),
            "sales": int(window["sales"].sum()), "months": int(len(window))}


def year_in_review(history, df=None, year=None):
    """A full annual snapshot for one calendar year: totals, YoY, best/worst
    months, the monthly series, and (when the file has a service column) the
    top-earning services for that year. Defaults to the latest year on record."""
    years = annual_summary(history)
    if not years:
        return None
    if year is None:
        year = years[-1]["year"]
    this = next((r for r in years if r["year"] == year), None)
    if this is None:
        return None

    h = history[history["month"].str[:4] == year].copy()
    monthly = [(r["month_label"], round(float(r["revenue"]), 0)) for _, r in h.iterrows()]
    best = h.loc[h["revenue"].idxmax()]
    worst = h.loc[h["revenue"].idxmin()]

    top_services = []
    if df is not None and "category" in df.columns and "month" in df.columns:
        yr = df[df["month"].str[:4] == year]
        if len(yr):
            by_cat = yr.groupby("category")["amount"].sum().sort_values(ascending=False)
            top_services = [(str(c), round(float(v), 0)) for c, v in by_cat.head(5).items()]

    return {"year": year, "revenue": this["revenue"], "sales": this["sales"],
            "avg_sale": this["avg_sale"], "months": this["months"], "yoy_pct": this["yoy_pct"],
            "best_label": best["month_label"], "best_revenue": round(float(best["revenue"]), 0),
            "worst_label": worst["month_label"], "worst_revenue": round(float(worst["revenue"]), 0),
            "monthly": monthly, "top_services": top_services,
            "available_years": [r["year"] for r in years]}
