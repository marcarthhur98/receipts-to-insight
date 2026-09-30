"""
main.py — Full Workflow Orchestrator (with charts)
==================================================

Runs the complete pipeline with one command:

    CSV file
      -> pandas analysis            (analyzer.py)
      -> charts                      (visualizer.py)
      -> executive Markdown report   (report_generator.py)
      -> AI insights & summary       (ai_summary.py)
      -> saved report                (outputs/report.md)

Run from the project root:
    python src/main.py
    python src/main.py data/sample.csv
    python src/main.py data/sample.csv --no-ai      (skip the AI step)
    python src/main.py data/sample.csv --no-charts  (skip chart generation)

main.py only coordinates; each module does its own work. If a step fails
(no API key, plotting issue), the pipeline degrades gracefully instead of
crashing.
"""

import argparse

from analyzer import load_csv, analyze
from visualizer import create_charts, render_ai_charts
from report_generator import build_report, save_report
from ai_summary import generate_ai_summary, suggest_charts


def run(csv_path="data/sample.csv", output_path="outputs/report.md",
        charts_dir="outputs/charts", use_ai=True, make_charts=True):
    """Run the full pipeline and save the report. Returns the saved path."""
    # --- Step 1: Load ---
    print(f"[1/5] Loading data from: {csv_path}")
    df = load_csv(csv_path)

    # --- Step 2: Analyse ---
    print("[2/5] Analysing dataset (stats + data quality)...")
    results = analyze(df)

    # --- Step 3: Charts ---
    charts = []
    if make_charts:
        print("[3/5] Generating charts...")
        try:
            charts = create_charts(df, charts_dir)
            print(f"      {len(charts)} chart(s) created in {charts_dir}/")
        except Exception as error:
            print(f"      Chart generation skipped: {error}")
    else:
        print("[3/5] Chart generation skipped (--no-charts).")

    # --- Optional: AI-suggested charts (AI picks relationships; we render them) ---
    if make_charts and use_ai:
        try:
            specs = suggest_charts(df)
            ai_charts = render_ai_charts(df, specs, charts_dir)
            if ai_charts:
                charts += ai_charts
                print(f"      {len(ai_charts)} AI-suggested chart(s) added.")
        except Exception as error:
            print(f"      AI chart suggestions skipped: {error}")

    # --- Step 4: Build the executive report ---
    print("[4/5] Building the executive report...")
    report_markdown = build_report(results, df, charts)

    # --- Step 5: AI summary (optional, graceful fallback) ---
    if use_ai:
        print("[5/5] Generating AI insights with Claude...")
        try:
            ai_text = generate_ai_summary(report_markdown)
            report_markdown += (
                "\n\n---\n\n# AI Executive Briefing (Claude)\n\n" + ai_text + "\n"
            )
            print("      AI insights added.")
        except Exception as error:
            report_markdown += (
                "\n\n---\n\n# AI Executive Briefing (Claude)\n\n"
                f"_AI step skipped: {error}_\n"
            )
            print(f"      AI step skipped: {error}")
    else:
        print("[5/5] AI step skipped (--no-ai).")
        report_markdown += (
            "\n\n---\n\n# AI Executive Briefing (Claude)\n\n"
            "_AI step skipped by user (--no-ai)._\n"
        )

    saved_path = save_report(report_markdown, output_path)
    print(f"\nDone. Report saved to: {saved_path}")
    return saved_path


def main():
    parser = argparse.ArgumentParser(
        description="Analyse a CSV and generate an AI-assisted executive report."
    )
    parser.add_argument("csv_path", nargs="?", default="data/sample.csv",
                        help="Path to the CSV file (default: data/sample.csv)")
    parser.add_argument("--output", default="outputs/report.md",
                        help=