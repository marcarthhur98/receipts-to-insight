# Version: executive-report v3 (schema-agnostic metrics, skew-aware insights)
"""
report_generator.py — Executive Report Generator (hardened)
===========================================================

Turns the analysis dict (+ optional charts) into a short, decision-oriented
Markdown report that works on ANY dataset, not just the operations sample.

Key upgrades over the first executive version:
  - Key Metrics and Executive Summary always carry useful, schema-agnostic
    content (numeric/categorical counts, overall missingness, dominant
    category) even when domain columns like Revenue are absent.
  - Outliers are reported as "skew" vs "outliers" with the share flagged.
  - Detects STRUCTURAL missingness: when several columns share an identical
    missing count, they likely apply only to a subset of records.

Sections: 1 Executive Summary, 2 Key Metrics, 3 Data Quality Snapshot,
4 Visual Analysis, 5 Main Insights, 6 Recommended Actions, 7 Technical Appendix.
"""

import os
from collections import Counter
from datetime import datetime


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def _money(v):
    return f"${v:,.0f}"


def _num(v, dp=2):
    return f"{v:,.{dp}f}"


# ---------------------------------------------------------------------------
# Small analytic helpers used across sections
# ---------------------------------------------------------------------------
def _dominant_category(results, n_rows):
    """Return (column, value, percent) for the single most dominant category."""
    best = None
    for col, vals in results["top_categories"].items():
        if not vals:
            continue
        value, count = next(iter(vals.items()))
        pct = count / n_rows * 100
        if best is None or pct > best[2]:
            best = (col, value, pct)
    return best


def _structural_missing(missing):
    """
    If two or more columns share an identical (non-zero) missing count, they
    probably apply only to a subset of records. Return (columns, count).
    """
    groups = Counter(m["count"] for m in missing.values())
    for count, how_many in groups.items():
        if how_many >= 2 and count > 0:
            cols = [c for c, m in missing.items() if m["count"] == count]
            return cols, count
    return None


# ---------------------------------------------------------------------------
# Section 1: Executive Summary
# ---------------------------------------------------------------------------
def section_executive_summary(results, df):
    info = results["basic_info"]
    quality = results["data_quality"]
    ct = results["column_types"]
    bullets = []

    scope = f"Dataset covers **{info['num_rows']:,} records** across {info['num_columns']} columns"
    extras = []
    if "Region" in df.columns:
        extras.append(f"{df['Region'].nunique()} regions")
    if "Department" in df.columns:
        extras.append(f"{df['Department'].nunique()} departments")
    if not extras:
        extras.append(f"{len(ct['numeric'])} numeric, {len(ct['categorical'])} categorical")
    bullets.append(scope + " (" + ", ".join(extras) + ").")

    if "Revenue" in df.columns:
        bullets.append(f"Total revenue of **{_money(df['Revenue'].sum())}**, "
                       f"averaging {_money(df['Revenue'].mean())} per record.")

    dom = _dominant_category(results, info["num_rows"])
    if dom and dom[2] >= 40:
        bullets.append(f"'{dom[0]}' is dominated by **{dom[1]}** ({dom[2]:.0f}% of records).")

    skew_cols = [c for c, o in quality["outliers"].items() if o["kind"] == "skew"]
    out_cols = [c for c, o in quality["outliers"].items() if o["kind"] == "outliers"]
    dq = (f"Data quality: {quality['duplicate_rows']['count']} duplicate row(s), "
          f"missing values in {len(results['missing_values'])} column(s)")
    if skew_cols:
        dq += f", {len(skew_cols)} skewed column(s)"
    if out_cols:
        dq += f", {len(out_cols)} column(s) with outliers"
    bullets.append(dq + " — see the Data Quality Snapshot.")

    sm = _structural_missing(results["missing_values"])
    if sm:
        bullets.append(f"{len(sm[0])} columns share an identical {sm[1]:,} missing values — likely "
                       f"fields that only apply to a subset of records, not random gaps.")

    return "\n".join(["## 1. Executive Summary", ""] + [f"- {b}" for b in bullets[:5]])


# ---------------------------------------------------------------------------
# Section 2: Key Metrics
# ---------------------------------------------------------------------------
def section_key_metrics(results, df):
    info = results["basic_info"]
    ct = results["column_types"]
    missing = results["missing_values"]

    total_cells = info["num_rows"] * info["num_columns"]
    total_missing = sum(m["count"] for m in missing.values())
    overall_missing = (total_missing / total_cells * 100) if total_cells else 0

    rows = [
        ("Rows", f"{info['num_rows']:,}"),
        ("Columns", str(info["num_columns"])),
        ("Numeric columns", str(len(ct["numeric"]))),
        ("Categorical columns", str(len(ct["categorical"]))),
        ("Overall missing", f"{overall_missing:.1f}%"),
    ]
    if "Revenue" in df.columns:
        rows.append(("Total Revenue", _money(df["Revenue"].sum())))
        rows.append(("Average Revenue", _money(df["Revenue"].mean())))
    if "Monthly_Cost" in df.columns:
        rows.append(("Average Monthly Cost", _money(df["Monthly_Cost"].mean())))
    if "Customer_Wait_Time" in df.columns:
        rows.append(("Average Wait Time (min)", _num(df["Customer_Wait_Time"].mean(), 1)))
    if "Satisfaction_Score" in df.columns:
        rows.append(("Average Satisfaction (0-10)", _num(df["Satisfaction_Score"].mean(), 1)))
    if "Number_of_Complaints" in df.columns:
        rows.append(("Total Complaints", f"{int(df['Number_of_Complaints'].sum()):,}"))

    lines = ["## 2. Key Metrics", "", "| Metric | Value |", "| --- | --- |"]
    lines += [f"| {label} | {value} |" for label, value in rows]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 3: Data Quality Snapshot
# ---------------------------------------------------------------------------
def section_data_quality_snapshot(results):
    q = results["data_quality"]
    missing = results["missing_values"]
    total_missing = sum(i["count"] for i in missing.values())

    skew = [c for c, o in q["outliers"].items() if o["kind"] == "skew"]
    outl = [c for c, o in q["outliers"].items() if o["kind"] == "outliers"]
    parts = []
    if outl:
        parts.append(f"{len(outl)} column(s): {', '.join(outl)}")
    if skew:
        parts.append(f"{len(skew)} skewed: {', '.join(skew)}")
    otext = "; ".join(parts) if parts else "none"

    dcols = q["possible_date_columns"]
    idcols = q["possible_id_columns"]
    return "\n".join([
        "## 3. Data Quality Snapshot", "",
        "| Check | Result |", "| --- | --- |",
        f"| Missing values | {total_missing:,} cell(s) across {len(missing)} column(s) |",
        f"| Duplicate rows | {q['duplicate_rows']['count']} |",
        f"| Outliers / skew | {otext} |",
        f"| ID-like columns (excluded from stats) | {', '.join(idcols) if idcols else 'none'} |",
        f"| Possible date columns | {', '.join(dcols) if dcols else 'none'} |",
    ])


# ---------------------------------------------------------------------------
# Section 4: Visual Analysis
# ---------------------------------------------------------------------------
def section_visual_analysis(charts):
    lines = ["## 4. Visual Analysis", ""]
    if not charts:
        lines.append("_No charts were generated for this dataset._")
        return "\n".join(lines)
    for c in charts:
        lines += [f"### {c['title']}", "", f"![{c['title']}]({c['path']})", "", c["description"], ""]
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Section 5: Main Insights
# ---------------------------------------------------------------------------
def section_main_insights(results, df):
    q = results["data_quality"]
    insights = []

    for col, o in q["outliers"].items():
        if o["kind"] == "skew":
            insights.append(f"**{col}** is right-skewed ({o['percent']}% of values beyond the IQR "
                            f"fence) — a long-tailed distribution rather than isolated errors.")
        else:
            insights.append(f"**{col}** has {o['count']} outlier(s) ({o['percent']}%), e.g. "
                            f"{o['example_values'][0]} (normal range "
                            f"[{o['lower_bound']}, {o['upper_bound']}]).")

    sm = _structural_missing(results["missing_values"])
    if sm:
        insights.append(f"Columns {', '.join(sm[0])} all miss exactly {sm[1]:,} values — they likely "
                        f"apply only to a subset of records (conditional fields), not random gaps.")

    if q["duplicate_rows"]["count"] > 0:
        insights.append(f"{q['duplicate_rows']['count']} duplicate row(s) were found.")

    if "Department" in df.columns and "Revenue" in df.columns:
        bd = df.groupby("Department")["Revenue"].sum()
        if not bd.empty:
            insights.append(f"**{bd.idxmax()}** generates the most revenue "
                            f"({bd.max() / bd.sum() * 100:.0f}% of total).")

    insights = insights[:5]
    lines = ["## 5. Main Insights", ""]
    lines += ([f"{i}. {t}" for i, t in enumerate(insights, 1)]
              if insights else ["No notable findings were automatically detected."])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 6: Recommended Actions
# ---------------------------------------------------------------------------
def section_recommended_actions(results, df):
    q = results["data_quality"]
    actions = []

    if q["duplicate_rows"]["count"] > 0:
        actions.append("Remove duplicate row(s) before reporting totals.")

    sm = _structural_missing(results["missing_values"])
    if sm:
        actions.append(f"Confirm whether {', '.join(sm[0])} are conditional fields; analyse them only "
                       f"on the applicable subset rather than imputing the {sm[1]:,} blanks.")
    elif results["missing_values"]:
        actions.append("Decide how to handle missing values (fill, drop, or flag).")

    skew = [c for c, o in q["outliers"].items() if o["kind"] == "skew"]
    outl = [c for c, o in q["outliers"].items() if o["kind"] == "outliers"]
    if outl:
        actions.append(f"Verify the outlier(s) in {', '.join(outl)} — entry errors or genuine events?")
    if skew:
        actions.append(f"Treat {', '.join(skew)} as skewed (consider median or a log scale, "
                       f"not outlier removal).")

    actions.append("Review the charts above to confirm these patterns before acting on them.")
    actions = actions[:5]
    lines = ["## 6. Recommended Actions", ""]
    lines += [f"{i}. {t}" for i, t in enumerate(actions, 1)]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 7: Technical Appendix
# ---------------------------------------------------------------------------
def section_technical_appendix(results):
    info = results["basic_info"]
    lines = ["## 7. Technical Appendix", "", "### Columns and Data Types", "",
             "| Column | Data Type |", "| --- | --- |"]
    for col, dtype in info["data_types"].items():
        lines.append(f"| {col} | {dtype} |")

    lines += ["", "### Numeric Summary (ID columns excluded)", ""]
    summary = results["numeric_summary"]
    if summary:
        lines += ["| Column | Count | Mean | Min | Max | Std Dev |",
                  "| --- | --- | --- | --- | --- | --