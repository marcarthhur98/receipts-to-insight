"""
app.py — Revenue & Growth (Streamlit)
=====================================

A simple tool for small businesses: upload your receipts/sales export and see
how much you make, where the money comes from, and how you're growing over time.
Built on the one record everyone keeps — receipts (a date + an amount). No
appointment status, no verdicts, no to-do lists.

Run from the project root:
    streamlit run app.py
"""

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from revenue_core import (load_receipts, normalize_receipts, validate_receipts,
                          summary, revenue_by_category, revenue_by_staff)
from revenue_history import save_snapshot, load_history, archive_upload
from revenue_charts import build_specs, render_specs, altair_chart, year_specs
from revenue_report import build_report, generate_recap, build_year_review
from revenue_trends import (annual_summary, same_month_last_year, trailing_12,
                            year_in_review)

CHARTS_DIR = "outputs/charts"

st.set_page_config(page_title="Revenue & Growth", page_icon="💰", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, [data-testid="stMetric"] { font-family: 'Inter', system-ui, sans-serif; }
#MainMenu, footer, [data-testid="stDecoration"] { visibility: hidden; }
.block-container { max-width: 1100px; padding-top: 2.4rem; padding-bottom: 4rem; }
.hero h1 { font-size: 1.95rem; font-weight: 700; letter-spacing: -0.022em; margin: 0 0 .15rem; }
.hero p { color: #667085; font-size: 1rem; margin: 0 0 .4rem; }
h2, h3 { font-weight: 600; letter-spacing: -0.012em; }
[data-testid="stMetric"] { background:#fff; border:1px solid #ECECF1; border-radius:16px;
    padding:16px 18px; box-shadow:0 1px 2px rgba(16,24,40,.05); }
[data-testid="stMetricLabel"] p { color:#667085; font-weight:500; font-size:.82rem; }
[data-testid="stMetricValue"] { font-weight:700; letter-spacing:-0.02em; }
.stTabs [data-baseweb="tab-list"] { gap:6px; }
.stTabs [data-baseweb="tab"] { font-weight:500; padding:6px 14px; }
.caption-muted { color:#667085; font-size:.9rem; }
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="hero"><h1>💰 Revenue &amp; Growth</h1>'
    '<p>Upload your receipts and see how much you make, where it comes from, and how you\'re growing.</p></div>',
    unsafe_allow_html=True,
)

uploaded = st.file_uploader("Upload your sales / receipts export (CSV)", type=["csv"])
if uploaded is None:
    st.info("Upload a CSV of your sales. All it needs is a **date** and an **amount** per sale — "
            "a service/item column unlocks the 'where your money comes from' breakdown.")
    st.stop()

try:
    raw = pd.read_csv(uploaded)
    df = normalize_receipts(raw)
except Exception as error:
    st.error(f"Could not read that file: {error}")
    st.stop()

missing = validate_receipts(df)
if missing:
    st.error(
        "This file is missing required column(s): **" + ", ".join(missing) + "**.  \n"
        "Detected columns: " + ", ".join(map(str, df.columns)) + ".  \n\n"
        "All the tool needs is a **date** and an **amount** per sale. Most receipt or "
        "sales exports have both."
    )
    st.stop()

go = st.button("Analyse", type="primary")
with st.expander(f"Preview — {len(df):,} sales", expanded=False):
    st.dataframe(raw.head(10), use_container_width=True)

if go:
    with st.spinner("Crunching your receipts..."):
        archive_upload(raw, getattr(uploaded, "name", "receipts"))  # keep a copy of the source file
        s = summary(df)
        history = None
        try:
            save_snapshot(df)
            history = load_history()
        except Exception as error:
            st.warning(f"History store unavailable: {error}")
        specs = build_specs(df, history)
        try:
            png_charts = render_specs(specs, CHARTS_DIR)
        except Exception as error:
            png_charts = []
            st.warning(f"Chart export skipped: {error}")
        report_md = build_report(df, history=history, charts=png_charts)
    st.session_state["rev"] = {
        "s": s, "specs": specs, "report_md": report_md,
        "by_category": revenue_by_category(df), "by_staff": revenue_by_staff(df),
        "history": history, "df": df,
        "months": 0 if history is None else len(history),
    }
    st.session_state.pop("recap", None)

state = st.session_state.get("rev")
if not state:
    st.stop()

s = state["s"]
specs = {sp["id"]: sp for sp in state["specs"]}
report_md = state["report_md"]

# ---------------- KPI strip ----------------
k = st.columns(4)
k[0].metric("Total revenue", f"${s['total_revenue']:,.0f}")
k[1].metric("Sales", f"{s['sales']:,}")
k[2].metric("Average sale", f"${s['avg_sale']:,.2f}")
k[3].metric("Months tracked", f"{state['months']}")

st.write("")
tab_overview, tab_growth, tab_year, tab_breakdown = st.tabs(
    ["  Overview  ", "  Growth  ", "  Year  ", "  Where the money comes from  "])

with tab_overview:
    if "revenue_by_category" in specs:
        with st.container(border=True):
            st.markdown("**Revenue by service**")
            st.altair_chart(altair_chart(specs["revenue_by_category"]), use_container_width=True)
            top = next(iter(state["by_category"].items()), None)
            if top:
                st.markdown(f'<div class="caption-muted">Top earner: {top[0]} '
                            f'(${top[1]["revenue"]:,.0f}, {top[1]["share"]}% of revenue).</div>',
                            unsafe_allow_html=True)
    else:
        st.caption("Add a service/item column to your export to see the revenue breakdown.")

with tab_growth:
    if "revenue_trend" in specs:
        with st.container(border=True):
            st.markdown("**Revenue by month**")
            st.altair_chart(altair_chart(specs["revenue_trend"]), use_container_width=True)
        growth_md = report_md.split("## Growth", 1)[1].split("## Where", 1)[0] if "## Growth" in report_md else ""
        if growth_md.strip():
            st.markdown("## Growth" + growth_md)
    else:
        st.caption("Once you've run a few months of data, your growth timeline appears here.")

with tab_year:
    history = state.get("history")
    years = annual_summary(history)
    if not years:
        st.caption("Your yearly view builds up as history accumulates. Upload receipts "
                   "across a few months and the annual picture appears here.")
    else:
        labels = [r["year"] for r in years]
        chosen = st.selectbox("Year", labels[::-1], index=0)  # newest first
        review = year_in_review(history, state.get("df"), chosen)
        yk = st.columns(4)
        yk[0].metric("Revenue this year", f"${review['revenue']:,.0f}",
                     None if review["yoy_pct"] is None else f"{review['yoy_pct']:+.1f}% YoY")
        yk[1].metric("Sales", f"{review['sales']:,}")
        yk[2].metric("Average sale", f"${review['avg_sale']:,.2f}")
        t12 = trailing_12(history)
        yk[3].metric("Trailing 12 mo", f"${t12['revenue']:,.0f}" if t12 else "—")

        sm = same_month_last_year(history)
        if sm:
            arrow = "▲" if (sm["pct"] or 0) > 0 else ("▼" if (sm["pct"] or 0) < 0 else "—")
            pct = "n/a" if sm["pct"] is None else f"{abs(sm['pct'])}%"
            st.markdown(f'<div class="caption-muted">Season-matched: <b>{sm["label"]}</b> '
                        f'${sm["revenue"]:,.0f} {arrow} {pct} vs <b>{sm["prior_label"]}</b> '
                        f'(${sm["prior_revenue"]:,.0f}).</div>', unsafe_allow_html=True)

        yspecs = {sp["id"]: sp for sp in year_specs(history, state.get("df"), chosen)}
        ids = [sid for sid in ("revenue_by_year", "year_monthly") if sid in yspecs]
        cols = st.columns(len(ids)) if len(ids) > 1 else [st.container()]
        for col, sid in zip(cols, ids):
            with col:
                st.altair_chart(altair_chart(yspecs[sid]), use_container_width=True)

        if review["top_services"]:
            st.markdown(f"**Top services in {chosen}**")
            st.dataframe(pd.DataFrame(review["top_services"], columns=["Service", "Revenue"]),
                         use_container_width=True, hide_index=True)

        review_md = build_year_review(history, state.get("df"), chosen)
        if review_md:
            st.download_button(f"Download {chosen} Year-in-Review (.md)", data=review_md,
                               file_name=f"year_in_review_{chosen}.md", mime="text/markdown",
                               key="dl_year")

with tab_breakdown:
    bc = state["by_category"]
    if bc:
        table = pd.DataFrame([
            {"Service": c, "Revenue": d["revenue"], "Share %": d["share"],
             "Sales": d["sales"], "Avg sale": d["avg_sale"]}
            for c, d in bc.items()])
        st.dataframe(table, use_container_width=True, hide_index=True)
    else:
        st.caption("No service/item column found, so revenue can't be broken down by service.")
    if state["by_staff"]:
        st.markdown("**By staff**")
        st.dataframe(pd.DataFrame([
            {"Staff": k2, "Revenue": v["revenue"], "Sales": v["sales"]}
            for k2, v in state["by_staff"].items()]), use_container_width=True, hide_index=True)

# ---------------- optional plain-English recap ----------------
with st.expander("📝 Plain-English summary (optional, uses Claude)", expanded=False):
    st.caption("A short, friendly recap of your numbers. Needs ANTHROPIC_API_KEY in .env.")
    if st.button("Write a summary"):
        try:
            st.session_state["recap"] = generate_recap(report_md)
        except Exception as error:
            st.session_state["recap"] = f"_Summary unavailable: {error}_"
    if st.session_state.get("recap"):
        st.markdown(st.session_state["recap"])

st.divider()
st.download_button("Download revenue summary (.md)", data=report_md,
                   file_name="revenue_summary.md", mime="text/markdown")
