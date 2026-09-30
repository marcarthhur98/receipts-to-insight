"""booking_main.py — run the salon booking pipeline end to end."""
import argparse
from booking_kpis import load_bookings, normalize_bookings, compute_all, validate_bookings
from booking_charts import create_booking_charts
from booking_health import assess
from booking_sales import compute_sales
from booking_report import build_booking_report, save_report, generate_booking_brief
from booking_history import save_snapshot, load_history, load_service_history, load_staff_history
from booking_config import BOOKING_HISTORY_DB

def run(csv_path="data/salon_bookings.csv", output_path="outputs/booking_report.md",
        charts_dir="outputs/charts", use_ai=True, history_db=BOOKING_HISTORY_DB):
    print(f"[1/5] Loading bookings: {csv_path}")
    df = normalize_bookings(load_bookings(csv_path))
    missing = validate_bookings(df)
    if missing:
        print(f"Error: file is missing required column(s): {', '.join(missing)}. "
              f"Detected: {', '.join(map(str, df.columns))}. "
              f"A status (completed/cancelled/no-show) and a date are required.")
        return None
    print("[2/5] Computing KPIs + health-check...")
    kpis = compute_all(df)
    sales = compute_sales(df)
    health = assess(df, kpis, sales)
    print("[3/5] Generating charts (incl. day x time heatmaps)...")
    charts = create_booking_charts(df, kpis, sales, charts_dir)
    print(f"      {len(charts)} chart(s).")
    history = service_history = staff_history = None
    try:
        save_snapshot(df, history_db)
        history = load_history(history_db)
        service_history = load_service_history(history_db)
        staff_history = load_staff_history(history_db)
        print(f"      history updated ({len(history)} weeks tracked).")
    except Exception as e:
        print(f"      history store unavailable: {e}")
    print("[4/5] Building weekly action brief...")
    report = build_booking_report(df, kpis, charts, health=health, sales=sales, history=history,
                                  service_history=service_history, staff_history=staff_history)
    if use_ai:
        print("[5/5] Generating AI action plan...")
        try:
            report += "\n\n---\n\n# AI Action Plan (Claude)\n\n" + generate_booking_brief(report) + "\n"
            print("      AI plan added.")
        except Exception as e:
            report += f"\n\n---\n\n# AI Action Plan (Claude)\n\n_AI step skipped: {e}_\n"
            print(f"      AI step skipped: {e}")
    else:
        print("[5/5] AI step skipped (--no-ai).")
        report += "\n\n---\n\n# AI Action Plan (Claude)\n\n_AI step skipped by user._\n"
    path = save_report(report, output_path)
    print(f"\nDone. Brief saved to: {path}")
    return path

def main():
    ap = argparse.ArgumentParser(description="Salon booking analytics → weekly action brief.")
    ap.add_argument("csv_path", nargs="?", default="data/salon_bookings.csv")
    ap.add_argument("--output", default="outputs/booking_report.md")
    ap.add_argument("--no-ai", action="store_true")
    a = ap.parse_args()
    try:
        run(a.csv_path, a.output, use_ai=not a.no_ai)
    except FileNotFoundError as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
