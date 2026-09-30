"""
app.py — Streamlit Web Interface (with charts + executive report)
=================================================================

Browser front-end. Upload a CSV, preview it, analyse it, view charts and the
executive report, then download the report.

Run from the project root:
    streamlit run app.py

This file is only the interface. The analysis, charts, report, and AI summary
all come from the same modules the command-line version uses.
"""

import os
import sys

import pandas as pd
import streamlit as st

# Make the modules in src/ importable from this root-level file.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from analyzer import analyze
from visualizer import create_charts, render_ai_charts
from report_generator import build_report
from ai_summary import generate_ai_summary, suggest_charts

CHARTS_DIR = "outputs/charts"


st.set_page_config(page_title="AI Data Insight Assistant", page_icon="📊")
st.title("📊 AI Data Insight Assistant")
st.write(
    "Upload a CSV file to get an executive-style analysis with charts and a "
    "plain-English insight report — optionally enhanced with AI."
)

# --- Step 1: Upload ---
uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])
if uploaded_file is None:
    st.info("Upload a CSV file to begin.")
    st.stop()

try:
    df = pd.read_csv(uploaded_file)
except Exception as error:
    st.error(f"Could not read that CSV file: {error}")
    st.stop()

# --- Step 2: Preview ---
st.subheader("Data preview")
st.write(f"**{df.shape[0]} rows × {df.shape[1]} columns**")
st.dataframe(df.head(10))

# --- Step 3: Options + Analyse ---
use_ai = st.checkbox(
    "Add AI insights (requires ANTHROPIC_API_KEY in your .env file)", value=False
)

if st.button("Analyse dataset"):
    with st.spinner("Analysing and generating charts..."):
        results = analyze(df)
        try:
            charts = create_charts(df, CHARTS_DIR)
        except Exception as error:
            charts = []
            st.warning(f"Chart generation skipped: {error}")

    # Optional: let the AI suggest extra charts (it picks; we render safely)
    if use_ai:
        with st.spinner("Asking Claude which charts to add..."):
            try:
                specs = suggest_charts(df)
                ai_charts = render_ai_charts(df, specs, CHARTS_DIR)
                if ai_charts:
                    charts += ai_charts
                    st.success(f"{len(ai_charts)} AI-suggested chart(s) added.")
            except Exception as error:
                st.warning(f"AI chart suggestions skipped: {error}")

    report_markdown = build_report(results, df, charts)

    # Optional AI briefing
    if use_ai:
        with st.spinner("Asking Claude for insights..."):
            try:
                ai_text = generate_ai_summary(report_markdown)
                report_markdown += (
                    "\n\n---\n\n# AI Executive Briefing (Claude)\n\n" + ai_text + "\n"
                )
                st.success("AI insights added.")
            except Exception as error:
                st.warning(f"AI step skipped: {error}")

    # --- Show charts natively (so they actually render in the browser) ---
    # chart["path"] is relative to the report (e.g. "charts/x.png"); the real
    # file lives in CHARTS_DIR, so rebuild the on-disk path for st.image.
    if charts:
        st.subheader("Charts")
        for chart in charts:
            image_path = os.path.join(CHARTS_DIR, os.path.basename(chart["path"]))
            st.image(image_path, caption=chart["title"], use_container_width=True)
            st.caption(chart["description"])

    # ---