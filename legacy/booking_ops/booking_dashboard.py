"""booking_dashboard.py — native (Altair) renderers for the dashboard.

Takes the same chart specs the matplotlib brief uses and builds themed Altair
charts that blend with the Streamlit page (transparent background, app fonts,
auto light/dark). One selection algorithm (booking_charts.select_chart_specs),
two renderers: matplotlib for the downloadable brief, Altair for the screen.
"""
import altair as alt
import pandas as pd

WD_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BLUE = "#3b6ea5"; HOT = "#c0504d"
HEIGHT = 260


def _finish(chart):
    return chart.properties(height=HEIGHT).configure_view(strokeWidth=0).configure(background="transparent")


def altair_chart(spec):
    """Return an Altair chart for a selected spec, or None if unsupported."""
    t = spec["type"]; d = spec["data"]

    if t == "heatmap":
        counts = d["counts"]
        idx = counts.index.name or "index"
        long = counts.reset_index().melt(id_vars=idx, var_name="hour", value_name="count")
        long["hour"] = long["hour"].astype(int)
        order = [w for w in WD_ORDER if w in list(counts.index)]
        chart = alt.Chart(long).mark_rect().encode(
            x=alt.X("hour:O", title="Hour"),
            y=alt.Y(f"{idx}:O", sort=order, title=None),
            color=alt.Color("count:Q", scale=alt.Scale(scheme="blues"), legend=None),
            tooltip=[idx, "hour", "count"],
        )
        return _finish(chart)

    if t == "line":
        df = pd.DataFrame({"hour": d["x"], "rate": d["y"]})
        chart = alt.Chart(df).mark_line(point=True, color=HOT).encode(
            x=alt.X("hour:N", sort=d["x"], title=d["xlabel"]),
            y=alt.Y("rate:Q", title=d["ylabel"]),
            tooltip=["hour", "rate"],
        )
        return _finish(chart)

    if t == "scatter":
        df = pd.DataFrame(d["points"], columns=["staff", "util", "rebook"])
        base = alt.Chart(df)
        pts = base.mark_circle(size=140, color=BLUE, opacity=0.85).encode(
            x=alt.X("util:Q", title=d["xlabel"], scale=alt.Scale(zero=False)),
            y=alt.Y("rebook:Q", title=d["ylabel"], scale=alt.Scale(zero=False)),
            tooltip=["staff", "util", "rebook"],
        )
        labels = base.mark_text(dx=9, dy=-6, fontSize=11).encode(
            x="util:Q", y="rebook:Q", text="staff")
        return _finish(pts + labels)

    if t == "pie":
        pairs = d["pairs"]; total = d.get("total") or sum(v for _, v in pairs) or 1
        df = pd.DataFrame({"service": [k for k, _ in pairs], "revenue": [v for _, v in pairs]})
        df["share"] = (df["revenue"] / total * 100).round(1)
        arc = alt.Chart(df).mark_arc(innerRadius=58, outerRadius=100).encode(
            theta=alt.Theta("revenue:Q", stack=True),
            color=alt.Color("service:N", title=None),
            tooltip=["service", alt.Tooltip("revenue:Q", title="Revenue", format="$,.0f"),
                     alt.Tooltip("share:Q", title="Share %")],
        )
        return _finish(arc)

    if t == "bar":
        df = pd.DataFrame(d["pairs"], columns=["category", "value"])
        chart = alt.Chart(df).mark_bar(color=d.get("color", HOT)).encode(
            x=alt.X("value:Q", title=d["xlabel"]),
            y=alt.Y("category:N", sort="-x", title=None),
            tooltip=["category", "value"],
        )
        return _finish(chart)

    return None
