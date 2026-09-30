"""booking_charts.py — the FIXED standard chart lineup (same four every week).

For a tool an owner opens weekly, predictability beats cleverness: the same four
charts appear in the same order every time, so they build a routine. The only
thing that adapts is which chart is HIGHLIGHTED as this week's focus, chosen by
mapping the top action to its chart.

Standard lineup:
  1. revenue_trend   (line)    — the growth pulse
  2. demand_heatmap  (heatmap) — when you're busy vs idle
  3. revenue_service (bar)     — where the money comes from
  4. staff_scorecard (scatter) — utilisation vs rebooking per staff

Matplotlib renders these for the downloadable brief; the app renders the same
specs natively with Altair (booking_dashboard.py).
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from booking_kpis import MIN_SUPPORT

BAR = "#3b6ea5"; HOT = "#c0504d"; FIG = (7, 4); DPI = 150
PIE_COLORS = ["#3b6ea5", "#c0504d", "#4f9d69", "#e0a23b", "#8064a2", "#4bacc6", "#9c5a3c", "#a5a5a5", "#d77fa1"]

# Which fixed chart a given health area points at (for the weekly highlight).
AREA_TO_CHART = {
    "No-shows": "demand_heatmap", "Schedule gaps": "demand_heatmap",
    "Cancellations": "revenue_service", "Service cancellations": "revenue_service",
    "Sales": "revenue_service", "Service yield": "revenue_service",
    "Revenue concentration": "revenue_service", "Service growth": "revenue_trend",
    "Utilization": "staff_scorecard", "Rebooking": "staff_scorecard",
    "Prime-time yield": "demand_heatmap",
}


def _rel(d, fn): return f"{os.path.basename(os.path.normpath(d))}/{fn}"
def _save(fig, d, fn):
    os.makedirs(d, exist_ok=True); fig.tight_layout(); fig.savefig(os.path.join(d, fn), dpi=DPI); plt.close(fig)
    return _rel(d, fn)


# ---------------- data builders ----------------
def _weekly_revenue(df):
    if "price" not in df.columns:
        return None
    c = df[df["status"] == "completed"]
    if "price" in c:
        c = c[c["price"].notna()]
    c = c.dropna(subset=["date"])
    if c.empty:
        return None
    w = c.set_index("date")["price"].resample("W").sum()
    if len(w) < 3:
        return None
    return {"x": [d.strftime("%b %d") for d in w.index],
            "y": [round(float(v), 0) for v in w.values],
            "xlabel": "Week ending", "ylabel": "Revenue ($)"}


def standard_chart_specs(df, kpis, sales):
    """The fixed four specs, in order. Any that genuinely can't be built is
    skipped, but normally all four are present."""
    specs = []

    rt = _weekly_revenue(df)
    if rt:
        specs.append({"id": "revenue_trend", "type": "line", "title": "Revenue trend (weekly)",
                      "description": "Total completed revenue per week — your growth pulse.",
                      "data": rt})

    counts = kpis["heatmap"]["counts"]
    if not counts.empty:
        specs.append({"id": "demand_heatmap", "type": "heatmap", "title": "Demand by day & time",
                      "description": "When you're busy vs idle — peak windows and gaps to fill.",
                      "data": {"counts": counts}})

    bys = sales.get("by_service") if sales else None
    if bys:
        ranked = sorted(((s, r["revenue"]) for s, r in bys.items()), key=lambda x: x[1], reverse=True)
        total = sum(v for _, v in ranked) or 1
        top, tail = ranked[:7], sum(v for _, v in ranked[7:])
        pairs = top + ([("Other", tail)] if tail > 0 else [])
        specs.append({"id": "revenue_service", "type": "pie", "title": "Revenue share by service",
                      "description": "Each service's share of total revenue this period.",
                      "data": {"pairs": pairs, "total": total}})

    util = kpis["utilization"]; reb = kpis["rebooking"]["by_staff"]
    both = [s for s in util if s in reb]
    if len(both) >= 3:
        pts = [(s, util[s]["utilization_pct"], reb[s]["rebooking_pct"]) for s in both]
        specs.append({"id": "staff_scorecard", "type": "scatter", "title": "Staff scorecard",
                      "description": "Utilisation vs rebooking per staff. Top-right are your stars.",
                      "data": {"points": pts, "xlabel": "Utilization (%)", "ylabel": "Rebooking (%)"}})

    return specs


def highlight_chart_id(health):
    """Pick the one chart to flag as this week's focus, from the top action."""
    for x in health.get("act", []):
        cid = AREA_TO_CHART.get(x["area"])
        if cid:
            return cid
    return None


# ---------------- matplotlib renderers ----------------
def _render_heatmap(spec, d):
    counts = spec["data"]["counts"]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    im = ax.imshow(counts.values, cmap="Blues", aspect="auto")
    ax.set_xticks(range(len(counts.columns))); ax.set_xticklabels([f"{h}:00" for h in counts.columns], fontsize=8)
    ax.set_yticks(range(len(counts.index))); ax.set_yticklabels(counts.index, fontsize=9)
    mx = counts.values.max()
    for i in range(counts.shape[0]):
        for j in range(counts.shape[1]):
            v = counts.values[i, j]
            ax.text(j, i, int(v), ha="center", va="center", fontsize=7,
                    color="white" if v > mx * 0.6 else "#333")
    ax.set_title(spec["title"]); fig.colorbar(im, fraction=0.025, pad=0.02)
    return _save(fig, d, f"bk_{spec['id']}.png")

def _render_line(spec, d):
    data = spec["data"]
    fig, ax = plt.subplots(figsize=FIG); ax.plot(data["x"], data["y"], marker="o", color=BAR)
    ax.set_title(spec["title"]); ax.set_xlabel(data["xlabel"]); ax.set_ylabel(data["ylabel"])
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right"); ax.grid(linestyle="--", alpha=0.4)
    return _save(fig, d, f"bk_{spec['id']}.png")

def _render_scatter(spec, d):
    pts = spec["data"]["points"]
    fig, ax = plt.subplots(figsize=FIG)
    ax.scatter([p[1] for p in pts], [p[2] for p in pts], color=BAR, s=80, edgecolor="white", zorder=3)
    for name, x, y in pts:
        ax.annotate(name, (x, y), textcoords="offset points", xytext=(5, 5), fontsize=8)
    ax.set_title(spec["title"]); ax.set_xlabel(spec["data"]["xlabel"]); ax.set_ylabel(spec["data"]["ylabel"])
    ax.grid(linestyle="--", alpha=0.4)
    return _save(fig, d, f"bk_{spec['id']}.png")

def _render_bar(spec, d):
    pairs = spec["data"]["pairs"]; names = [k for k, _ in pairs]; vals = [v for _, v in pairs]
    fig, ax = plt.subplots(figsize=FIG)
    ax.barh(names[::-1], vals[::-1], color=spec["data"].get("color", BAR))
    ax.set_title(spec["title"]); ax.set_xlabel(spec["data"]["xlabel"]); ax.grid(axis="x", linestyle="--", alpha=0.4)
    return _save(fig, d, f"bk_{spec['id']}.png")

def _render_pie(spec, d):
    pairs = spec["data"]["pairs"]
    names = [k for k, _ in pairs]; vals = [v for _, v in pairs]
    total = sum(vals) or 1
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    colors = [PIE_COLORS[i % len(PIE_COLORS)] for i in range(len(vals))]
    wedges, _, autotexts = ax.pie(
        vals, startangle=90, counterclock=False, colors=colors,
        wedgeprops=dict(width=0.42, edgecolor="white"),
        autopct=lambda pct: f"{pct:.0f}%" if pct >= 4 else "",
        pctdistance=0.79, textprops=dict(fontsize=8, color="white", weight="bold"))
    ax.set_title(spec["title"]); ax.set_aspect("equal")
    labels = [f"{n} — ${v:,.0f}" for n, v in pairs]
    ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8, frameon=False)
    return _save(fig, d, f"bk_{spec['id']}.png")


_RENDERERS = {"heatmap": _render_heatmap, "line": _render_line, "scatter": _render_scatter,
              "bar": _render_bar, "pie": _render_pie}


def render_specs(specs, output_dir="outputs/charts"):
    charts = []
    for spec in specs:
        path = _RENDERERS[spec["type"]](spec, output_dir)
        charts.append({"id": spec["id"], "title": spec["title"], "path": path,
                       "description": spec["description"], "type": spec["type"]})
    return charts


def create_booking_charts(df, kpis, sales, output_dir="outputs/charts"):
    """Render the fixed standard lineup to PNG (for the downloadable brief)."""
    return render_specs(standard_chart_specs(df, kpis, sales), output_dir)
