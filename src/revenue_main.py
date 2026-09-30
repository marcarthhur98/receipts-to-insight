"""revenue_main.py — run the revenue summary from the command line.

    python src/revenue_main.py                      # uses data/sales_receipts.csv
    python src/revenue_main.py path/to/receipts.csv
"""
import argparse

from revenue_core import load_receipts, normalize_receipts, validate_receipts
from revenue_history import save_snapshot, load_history, archive_upload, DB_DEFAULT
from revenue_charts import build_specs, render_specs
from revenue_report import build_report, save_report


def run(csv_path="data/sales_receipts.csv", output_path="outputs/revenue_report.md",
        charts_dir="outputs/charts", history_db=DB_DEFAULT):
    print(f"[1/4] Loading receipts: {csv_path}")
    raw = load_receipts(csv_path)
    archived = archive_upload(raw, csv_path)
    if archived:
        print(f"      archived a copy to {archived}")
    df = normalize_receipts(raw)
    missing = validate_receipts(df)
    if missing:
        print(f"Error: file is missing required column(s): {', '.join(missing)}. "
              f"Detected: {', '.join(map(str, df.columns))}. A date and an amount are required.")
        return None
    print(f"      {len(df):,} sales loaded.")
    history = None
    try:
        save_snapshot(df, history_db)
        history = load_history(history_db)
        print(f"      history updated ({len(history)} months tracked).")
    except Exception as e:
        print(f"      history store unavailable: {e}")
    print("[2/4] Building charts...")
    charts = render_specs(build_specs(df, history), charts_dir)
    print("[3/4] Building revenue summary...")
    report = build_report(df, history=history, charts=charts)
    path = save_report(report, output_path)
    print(f"[4/4] Done. Saved to: {path}")
    return path


def main():
    ap = argparse.ArgumentParser(description="Summarise revenue from a receipts/transactions CSV.")
    ap.add_argument("csv_path", nargs="?", default="data/sales_receipts.csv")
    ap.add_argument("--output", default="outputs/revenue_report.md")
    a = ap.parse_args()
    run(a.csv_path, a.output)


if __name__ == "__main__":
    main()
