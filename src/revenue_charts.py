"""revenue_charts.py — the two core visuals: the growth timeline and the
'where the money comes from' breakdown. Matplotlib renders PNGs for the
downloadable report; the app renders the same specs natively with Altair.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import altair as alt
import pandas as pd
from revenue_core import revenue_by_category
from revenue_trends import annual_summary, year_in_review

BLUE = "#2F6FED"; DPI = 150; FIG = (7, 4)


def build_specs(df, history):
    """Data-only chart specs: revenue timeline (from the persistent history) and
    revenue by service (from the current receipts)."""
    specs = []
    if history is not None and len(history) >= 2:
        specs.append({"id": "revenue_trend", "type": "line", "title": "Revenue by month",
                      "description": "Your revenue over time — the growth picture.",
                      "data": {"x": list(history["month_label"]),
                               "y": [round(float(v)) for v in history["revenue"]],
                               "xlabel": "Month", "ylabel": "Revenue ($)"}})
    bc = revenue_by_category(df)
    if bc:
        pairs = [(c, d["revenue"]) for c, d in list(bc.items())[:8]]
        specs.append({"id": "revenue_by_category", "type": "bar", "title": "Revenue by service",
                      "description": "Where your money comes from this period.",
                      "data": {"pairs": pairs, "xlabel": "Revenue ($)"}})
    return specs


def year_specs(history, df=None, year=None):
    """Charts for the yearly perspective: revenue per calendar year, and the
    selected year broken down month by month."""
    specs = []
    years = annual_summary(history)
    if len(years) >= 2:
        specs.append({"id": "revenue_by_year", "type": "vbar", "title": "Revenue by year",
                      "description": "Your annual revenue at a glance.",
                      "data": {"pairs": [(r["year"], r["revenue"]) for r in years],
                               "xlabel": "Year", "ylabel": "Revenue ($)"}})
    review = year_in_review(history, df, year)
    if review and review["monthly"]:
        specs.append({"id": "year_monthly", "type": "vbar", "title": f"{review['year']} by month",
                      "description": f"How {review['year']} unfolded month by month.",
                      "data": {"pairs": review["monthly"], "xlabel": "Month", "ylabel": "Revenue ($)"}})
    return specs


# ---------------- matplotlib (for the downloadable report) ----------------
def _rel(d, fn): return f"{os.path.basename(os.path.normpath(d))}/{fn}"
def _save(fig, d, fn):
    os.makedirs(d, exist_ok=True); fig.tight_layout(); fig.savefig(os.path.join(d, fn), dpi=DPI); plt.close(fig)
    return _rel(d, fn)


def _render_line(spec, d):
    data = spec["data"]
    fig, ax = plt.subplots(figsize=FIG)
    ax.plot(data["x"], data["y"], marker="o", color=BLUE)
    ax.set_title(spec["title"]); ax.set_xlabel(data["xlabel"]); ax.set_ylabel(data["ylabel"])
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right"); ax.grid(linestyle="--", alpha=0.4)
    return _save(fig, d, f"rev_{spec['id']}.png")


def _render_bar(spec, d):
    pairs = spec["data"]["pairs"]; names = [k for k, _ in pairs]; vals = [v for _, v in pairs]
    fig, ax = plt.subplots(figsize=FIG)
    ax.barh(names[::-1], vals[::-1], color=BLUE)
    ax.set_title(spec["title"]); ax.set_xlabel(spec["data"]["xlabel"]); ax.grid(axis="x", linestyle="--", alpha=0.4)
    return _save(fig, d, f"rev_{spec['id']}.png")


def _render_vbar(spec, d):
    pairs = spec["data"]["pairs"]; names = [str(k) for k, _ in pairs]; vals = [v for _, v in pairs]
    fig, ax = plt.subplots(figsize=FIG)
    ax.bar(names, vals, color=BLUE)
    ax.set_title(spec["title"]); ax.set_xlabel(spec["data"]["xlabel"]); ax.set_ylabel(spec["data"]["ylabel"])
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right"); ax.grid(axis="y", linestyle="--", alpha=0.4)
    return _save(fig, d, f"rev_{spec['id']}.png")


_RENDERERS = {"line": _render_line, "bar": _render_bar, "vbar": _render_vbar}


def render_specs(specs, output_dir="outputs/charts"):
    charts = []
    for spec in specs:
        charts.append({"id": spec["id"], "title": spec["title"],
                       "path": _RENDERERS[spec["type"]](spec, output_dir),
                       "description": spec["description"], "type": spec["type"]})
    return charts


# ---------------- Altair (for the app, theme-native) ----------------
def altair_chart(spec):
    t, d = spec["type"], spec["data"]
    if t == "line":
        df = pd.DataFrame({"month": d["x"], "revenue": d["y"]})
        chart = alt.Chart(df).mark_line(point=True, color=BLUE).encode(
            x=alt.X("month:N", sort=d["x"], title=d["xlabel"]),
            y=alt.Y("revenue:Q", title=d["ylabel"]),
            tooltip=["month", alt.Tooltip("revenue:Q", format="$,.0f")])
    elif t == "bar":
        df = pd.DataFrame(d["pairs"], columns=["service", "revenue"])
        chart = alt.Chart(df).mark_bar(color=BLUE).encode(
            x=alt.X("revenue:Q", title=d["xlabel"]),
            y=alt.Y("service:N", sort="-x", title=None),
            tooltip=["service", alt.Tooltip("revenue:Q", format="$,.0f")])
    elif t == "vbar":
        order = [str(k) for k, _ in d["pairs"]]
        df = pd.DataFrame({"label": order, "revenue": [v for _, v in d["pairs"]]})
        chart = alt.Chart(df).mark_bar(color=BLUE).encode(
            x=alt.X("label:N", sort=order, title=d["xlabel"]),
            y=alt.Y("revenue:Q", title=d["ylabel"]),
            tooltip=["label", alt.Tooltip("revenue:Q", format="$,.0f")])
    else:
        return None
    return chart.properties(height=300).configure_view(strokeWidth=0).configure(background="transparent")
