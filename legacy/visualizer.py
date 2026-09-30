"""
visualizer.py — Visualization Module (domain + schema-agnostic)
===============================================================

Generates clean matplotlib charts and returns, for each one, a dict:
    {"title": ..., "path": "charts/x.png", "description": ...}

Two families of charts:
  - DOMAIN-SPECIFIC: fire only when the expected columns exist (e.g. Revenue
    by Department). Great for the operations sample.
  - GENERIC (schema-agnostic): work on ANY dataset — missingness, correlation
    heatmap, top categories, numeric distributions. These guarantee the report
    always has useful visuals, even on data the tool has never seen.

create_charts() runs the domain charts first, then fills the rest with generic
charts up to a cap, so the output stays focused instead of dumping dozens.

ID-like columns are excluded from numeric charts (an ID has no meaningful
distribution or correlation).
"""

import os

import matplotlib

matplotlib.use("Agg")  # non-interactive backend; works in scripts and Streamlit
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

# Chart types the AI is allowed to request (the renderer validates each one).
ALLOWED_AI_CHARTS = {"scatter", "bar", "line", "hist", "box"}

BAR_COLOR = "#3b6ea5"
ACCENT_COLOR = "#c0504d"
FIG_SIZE = (7, 4)
DPI = 150
MIN_TREND_PERIODS = 4
MAX_CHARTS = 8
MIN_NONNULL = 30  # a column needs this many real values before we chart its distribution


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _ensure_dir(d):
    os.makedirs(d, exist_ok=True)


def _rel(output_dir, filename):
    """Path used inside the Markdown report (e.g. 'charts/x.png')."""
    return f"{os.path.basename(os.path.normpath(output_dir))}/{filename}"


def _save(fig, output_dir, filename):
    _ensure_dir(output_dir)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, filename), dpi=DPI)
    plt.close(fig)
    return _rel(output_dir, filename)


def _has(df, *cols):
    return all(c in df.columns for c in cols)


def _id_like(df):
    """Same ID heuristic as the analyzer, kept here so the module is standalone."""
    out = []
    n = len(df)
    for col in df.columns:
        all_unique = df[col].nunique(dropna=True) == n
        is_float = str(df[col].dtype).startswith("float")
        if "id" in col.lower() or (all_unique and not is_float):
            out.append(col)
    return set(out)


def _numeric_cols(df):
    ids = _id_like(df)
    return [c for c in df.select_dtypes(include="number").columns if c not in ids]


def _reliable_numeric_cols(df):
    """Numeric (non-ID) columns with enough non-null, non-constant data to chart honestly."""
    out = []
    for c in _numeric_cols(df):
        s = df[c].dropna()
        if len(s) >= MIN_NONNULL and s.nunique() >= 2:
            out.append(c)
    return out


def _categorical_cols(df, lo=2, hi=15):
    """Object columns with a sensible number of categories to chart."""
    ids = _id_like(df)
    out = []
    for c in df.select_dtypes(include="object").columns:
        if c in ids:
            continue
        if lo <= df[c].nunique(dropna=True) <= hi:
            out.append(c)
    return out


# ===========================================================================
# DOMAIN-SPECIFIC CHARTS
# ===========================================================================
def plot_revenue_by_department(df, d):
    if not _has(df, "Department", "Revenue"):
        return None
    data = df.groupby("Department")["Revenue"].sum().sort_values(ascending=False)
    if data.empty:
        return None
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.bar(data.index, data.values, color=BAR_COLOR)
    ax.set_title("Total Revenue by Department")
    ax.set_xlabel("Department"); ax.set_ylabel("Total Revenue")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    return {"title": "Revenue by Department", "path": _save(fig, d, "revenue_by_department.png"),
            "description": "Shows which department contributes the most total revenue."}


def plot_wait_time_by_region(df, d):
    if not _has(df, "Region", "Customer_Wait_Time"):
        return None
    data = df.groupby("Region")["Customer_Wait_Time"].mean().sort_values(ascending=False)
    if data.empty:
        return None
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.bar(data.index, data.values, color=BAR_COLOR)
    ax.set_title("Average Customer Wait Time by Region")
    ax.set_xlabel("Region"); ax.set_ylabel("Avg Wait Time (min)")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    return {"title": "Average Wait Time by Region", "path": _save(fig, d, "wait_time_by_region.png"),
            "description": "Compares average wait times across regions to locate bottlenecks."}


def plot_satisfaction_by_department(df, d):
    if not _has(df, "Department", "Satisfaction_Score"):
        return None
    data = df.groupby("Department")["Satisfaction_Score"].mean().sort_values(ascending=False)
    if data.empty:
        return None
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.bar(data.index, data.values, color=BAR_COLOR)
    ax.set_title("Average Satisfaction by Department")
    ax.set_xlabel("Department"); ax.set_ylabel("Avg Satisfaction (0-10)")
    ax.set_ylim(0, 10); ax.grid(axis="y", linestyle="--", alpha=0.4)
    return {"title": "Satisfaction by Department", "path": _save(fig, d, "satisfaction_by_department.png"),
            "description": "Compares customer satisfaction across departments."}


def plot_revenue_vs_cost(df, d):
    if not _has(df, "Monthly_Cost", "Revenue"):
        return None
    data = df[["Monthly_Cost", "Revenue"]].dropna()
    if data.empty:
        return None
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.scatter(data["Monthly_Cost"], data["Revenue"], color=BAR_COLOR, alpha=0.75, edgecolor="white")
    ax.set_title("Revenue vs Monthly Cost")
    ax.set_xlabel("Monthly Cost"); ax.set_ylabel("Revenue")
    ax.grid(linestyle="--", alpha=0.4)
    return {"title": "Revenue vs Monthly Cost", "path": _save(fig, d, "revenue_vs_cost.png"),
            "description": "Tests whether higher spending is associated with higher revenue."}


def plot_wait_time_vs_satisfaction(df, d):
    if not _has(df, "Customer_Wait_Time", "Satisfaction_Score"):
        return None
    data = df[["Customer_Wait_Time", "Satisfaction_Score"]].dropna()
    if data.empty:
        return None
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.scatter(data["Customer_Wait_Time"], data["Satisfaction_Score"],
               color=ACCENT_COLOR, alpha=0.75, edgecolor="white")
    ax.set_title("Customer Wait Time vs Satisfaction")
    ax.set_xlabel("Wait Time (min)"); ax.set_ylabel("Satisfaction (0-10)")
    ax.grid(linestyle="--", alpha=0.4)
    return {"title": "Wait Time vs Satisfaction", "path": _save(fig, d, "wait_time_vs_satisfaction.png"),
            "description": "Tests whether longer wait times go with lower satisfaction."}


def plot_revenue_trend(df, d):
    if not _has(df, "Date", "Revenue"):
        return None
    dates = pd.to_datetime(df["Date"], errors="coerce")
    t = pd.DataFrame({"p": dates.dt.to_period("M"), "Revenue": df["Revenue"]}).dropna()
    monthly = t.groupby("p")["Revenue"].sum().sort_index()
    if len(monthly) < MIN_TREND_PERIODS:
        return None
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.plot(monthly.index.astype(str), monthly.values, marker="o", color=BAR_COLOR)
    ax.set_title("Monthly Revenue Trend")
    ax.set_xlabel("Month"); ax.set_ylabel("Total Revenue")
    ax.grid(linestyle="--", alpha=0.4)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    return {"title": "Monthly Revenue Trend", "path": _save(fig, d, "revenue_trend.png"),
            "description": "Shows whether revenue is growing, declining, or unstable over time."}


# ===========================================================================
# GENERIC (SCHEMA-AGNOSTIC) CHARTS
# ===========================================================================
def plot_missing_values(df, d):
    miss = (df.isnull().mean() * 100)
    miss = miss[miss > 0].sort_values(ascending=False).head(15)
    if miss.empty:
        return None
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.barh(miss.index[::-1], miss.values[::-1], color=ACCENT_COLOR)
    ax.set_title("Missing Values by Column"); ax.set_xlabel("% Missing")
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    return {"title": "Missing Values by Column", "path": _save(fig, d, "missing_values.png"),
            "description": ("Share of missing data per column. Columns with identical, high "
                            "missingness often indicate fields that only apply to a subset of records.")}


def plot_correlation_heatmap(df, d):
    cols = _reliable_numeric_cols(df)
    if len(cols) < 2:
        return None
    # Drop columns that can't form a valid correlation (e.g. fields present only
    # for a non-overlapping subset of rows, which produce all-NaN correlations).
    corr = df[cols].corr().dropna(how="all").dropna(axis=1, how="all")
    if corr.shape[0] < 2:
        return None
    cols = list(corr.columns)
    size = max(5, len(cols) * 0.6)
    fig, ax = plt.subplots(figsize=(size, size))
    # Mask pairs with no overlapping data (NaN) so they show as gray "no data"
    # instead of a misleading zero.
    cmap = plt.get_cmap("RdBu").copy()
    cmap.set_bad("#dddddd")
    data = np.ma.masked_invalid(corr.values)
    im = ax.imshow(data, cmap=cmap, vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols))); ax.set_xticklabels(cols, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(cols))); ax.set_yticklabels(cols, fontsize=8)
    if len(cols) <= 10:  # annotate only when it stays readable
        for i in range(len(cols)):
            for j in range(len(cols)):
                val = corr.values[i, j]
                if np.isnan(val):
                    continue
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7,
                        color="white" if abs(val) > 0.5 else "black")
    ax.set_title("Correlation Between Numeric Columns")
    fig.colorbar(im, fraction=0.046, pad=0.04)
    return {"title": "Correlation Heatmap", "path": _save(fig, d, "correlation_heatmap.png"),
            "description": ("How numeric columns move together (-1 to 1). Gray cells mean too little "
                            "overlapping data to judge. Strong pairs are candidates for deeper analysis.")}


def plot_category_bar(df, d, col):
    counts = df[col].value_counts().head(10)
    if counts.empty:
        return None
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.bar(counts.index.astype(str), counts.values, color=BAR_COLOR)
    ax.set_title(f"Top Values: {col}")
    ax.set_xlabel(col); ax.set_ylabel("Count")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    safe = col.replace(" ", "_")
    return {"title": f"Top Values — {col}", "path": _save(fig, d, f"top_{safe}.png"),
            "description": f"The most common categories in '{col}', showing how records are distributed."}


def plot_histogram(df, d, col):
    s = df[col].dropna()
    # Skip columns that are too sparse or effectively constant — a histogram of
    # those is noise, not signal.
    if len(s) < MIN_NONNULL or s.nunique() < 2:
        return None
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.hist(s, bins=30, color=BAR_COLOR, edgecolor="white")
    ax.set_title(f"Distribution: {col}")
    ax.set_xlabel(col); ax.set_ylabel("Frequency")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    safe = col.replace(" ", "_")
    return {"title": f"Distribution — {col}", "path": _save(fig, d, f"dist_{safe}.png"),
            "description": f"The distribution of '{col}'. A long tail signals skew rather than isolated outliers."}


# ===========================================================================
# Curator
# ===========================================================================
def create_charts(df, output_dir="outputs/charts", max_charts=MAX_CHARTS):
    """
    Build a focused set of charts for any dataset: domain-specific ones first
    (when their columns exist), then generic charts to fill up to max_charts.
    Returns a list of {title, path, description} dicts.
    """
    charts = []

    # 1) Domain-specific (self-skip when columns are absent)
    for build in [plot_revenue_by_department, plot_wait_time_by_region,
                  plot_satisfaction_by_department, plot_revenue_vs_cost,
                  plot_wait_time_vs_satisfaction, plot_revenue_trend]:
        result = build(df, output_dir)
        if result:
            charts.append(result)

    # 2) Generic fallbacks (work on any schema)
    generic = []
    mv = plot_missing_values(df, output_dir)
    if mv:
        generic.append(mv)
    ch = plot_correlation_heatmap(df, output_dir)
    if ch:
        generic.append(ch)
    for col in _categorical_cols(df)[:2]:
        r = plot_category_bar(df, output_dir, col)
        if r:
            generic.append(r)
    # Numeric histograms, most variable columns first (reliable columns only)
    for col in sorted(_reliable_numeric_cols(df), key=lambda c: df[c].std(skipna=True), reverse=True):
        r = plot_histogram(df, output_dir, col)
        if r:
            generic.append(r)

    for g in generic:
        if len(charts) >= max_charts:
            break
        charts.append(g)
    return charts[:max_charts]


# ===========================================================================
# AI-SUGGESTED CHARTS (r