"""booking_history.py — local weekly history store (SQLite).

A thin interface over a single local .db file. Each run computes weekly
aggregates for every week in the upload and UPSERTS them by week-ending date,
so the history self-corrects no matter how often files are uploaded — you get a
clean, continuous weekly time series with no duplicates.

Kept deliberately behind save_snapshot()/load_history() so the rest of the app
never knows where data lives; swapping to a cloud database later is a one-file
change.
"""
import os
import sqlite3
from datetime import datetime

import pandas as pd
from booking_config import BOOKING_HISTORY_DB

COLUMNS = ["week_ending", "revenue", "appointments", "completed", "worked_hours",
           "no_show_rate", "cancellation_rate", "avg_ticket"]


def _weekly_aggregates(df):
    """Headline metrics per ISO week (week-ending date) from one upload."""
    res = df[df["status"].isin(["completed", "cancelled", "no_show"])].dropna(subset=["date"])
    comp = df[df["status"] == "completed"].dropna(subset=["date"])
    if res.empty:
        return []
    res = res.assign(week=res["date"].dt.to_period("W").apply(lambda p: p.end_time.date().isoformat()))
    comp = comp.assign(week=comp["date"].dt.to_period("W").apply(lambda p: p.end_time.date().isoformat()))

    agg = {}
    for wk, g in res.groupby("week"):
        agg[wk] = {"week_ending": wk, "appointments": int(len(g)),
                   "no_show_rate": round(float((g["status"] == "no_show").mean()) * 100, 1),
                   "cancellation_rate": round(float((g["status"] == "cancelled").mean()) * 100, 1),
                   "revenue": 0.0, "completed": 0, "worked_hours": 0.0, "avg_ticket": 0.0}
    for wk, g in comp.groupby("week"):
        rev = float(g["price"].sum()) if "price" in g else 0.0
        hrs = float(g["duration_min"].sum()) / 60 if "duration_min" in g else 0.0
        n = int(len(g))
        a = agg.setdefault(wk, {"week_ending": wk, "appointments": 0, "no_show_rate": 0.0,
                                "cancellation_rate": 0.0})
        a["revenue"] = round(rev, 2); a["completed"] = n
        a["worked_hours"] = round(hrs, 1); a["avg_ticket"] = round(rev / n, 2) if n else 0.0
    return sorted(agg.values(), key=lambda r: r["week_ending"])


def init_db(path=BOOKING_HISTORY_DB):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE IF NOT EXISTS weekly (
        week_ending TEXT PRIMARY KEY, revenue REAL, appointments INTEGER, completed INTEGER,
        worked_hours REAL, no_show_rate REAL, cancellation_rate REAL, avg_ticket REAL,
        updated_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS weekly_service (
        week_ending TEXT, service TEXT, revenue REAL, bookings INTEGER, no_show_rate REAL,
        updated_at TEXT, PRIMARY KEY (week_ending, service))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS weekly_staff (
        week_ending TEXT, staff TEXT, revenue REAL, bookings INTEGER,
        updated_at TEXT, PRIMARY KEY (week_ending, staff))""")
    return conn


def save_snapshot(df, path=BOOKING_HISTORY_DB):
    """Upsert weekly aggregates from this upload into the store."""
    conn = init_db(path)
    now = datetime.now().isoformat(timespec="seconds")
    for a in _weekly_aggregates(df):
        conn.execute("""INSERT OR REPLACE INTO weekly
            (week_ending, revenue, appointments, completed, worked_hours,
             no_show_rate, cancellation_rate, avg_ticket, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (a["week_ending"], a["revenue"], a["appointments"], a["completed"],
             a["worked_hours"], a["no_show_rate"], a["cancellation_rate"], a["avg_ticket"], now))
    for r in _service_weekly(df):
        conn.execute("""INSERT OR REPLACE INTO weekly_service
            (week_ending, service, revenue, bookings, no_show_rate, updated_at)
            VALUES (?,?,?,?,?,?)""",
            (r["week_ending"], r["service"], r["revenue"], r["bookings"], r["no_show_rate"], now))
    for r in _staff_weekly(df):
        conn.execute("""INSERT OR REPLACE INTO weekly_staff
            (week_ending, staff, revenue, bookings, updated_at)
            VALUES (?,?,?,?,?)""",
            (r["week_ending"], r["staff"], r["revenue"], r["bookings"], now))
    conn.commit(); conn.close()
    return path


def load_history(path=BOOKING_HISTORY_DB):
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)
    conn = sqlite3.connect(path)
    try:
        h = pd.read_sql_query("SELECT * FROM weekly ORDER BY week_ending", conn)
    except Exception:
        h = pd.DataFrame(columns=COLUMNS)
    conn.close()
    return h


def week_over_week(history):
    """True change between the two most recent stored weeks, or None."""
    if len(history) < 2:
        return None
    last, prev = history.iloc[-1], history.iloc[-2]

    def block(col, as_int=False):
        delta = last[col] - prev[col]
        cast = int if as_int else (lambda v: round(float(v), 1))
        return {"prev": cast(prev[col]), "recent": cast(last[col]), "delta": cast(delta)}

    return {"last_week": last["week_ending"], "prev_week": prev["week_ending"],
            "revenue": block("revenue"), "appointments": block("appointments", as_int=True),
            "worked_hours": block("worked_hours"), "no_show_rate": block("no_show_rate")}


def monthly_history(history):
    """Roll the weekly store up to a month-by-month timeline. Sums revenue,
    appointments, completed, and worked hours; weights rates by volume."""
    if history is None or len(history) == 0:
        return pd.DataFrame(columns=["month", "month_label", "revenue", "appointments",
                                     "completed", "worked_hours", "no_show_rate", "avg_ticket"])
    h = history.copy()
    h["month"] = pd.to_datetime(h["week_ending"]).dt.to_period("M").astype(str)
    g = h.groupby("month")
    out = pd.DataFrame({
        "month": g.size().index,
        "revenue": g["revenue"].sum().round(2).values,
        "appointments": g["appointments"].sum().astype(int).values,
        "completed": g["completed"].sum().astype(int).values,
        "worked_hours": g["worked_hours"].sum().round(1).values,
    })
    appts = g["appointments"].sum().replace(0, 1)
    out["no_show_rate"] = ((h["no_show_rate"] * h["appointments"]).groupby(h["month"]).sum() / appts).round(1).values
    out["avg_ticket"] = (out["revenue"] / out["completed"].replace(0, 1)).round(2)
    out["month_label"] = pd.to_datetime(out["month"] + "-01").dt.strftime("%b %Y")
    return out.sort_values("month").reset_index(drop=True)


# ---------------- per-service & per-provider history (deeper grain) ----------------
def has_usable_staff(df):
    """True only if the export carries a real, populated staff/provider column.
    We never ask the owner to enter it — we just use it when their booking system
    already records it (most do)."""
    if "staff" not in df.columns:
        return False
    s = df["staff"].dropna().astype(str)
    s = s[s.str.strip() != ""]
    return len(s) >= 0.7 * len(df) and s.nunique() >= 2


def _service_weekly(df):
    if "service" not in df.columns:
        return []
    res = df[df["status"].isin(["completed", "cancelled", "no_show"])].dropna(subset=["date"])
    if res.empty:
        return []
    res = res.assign(week=res["date"].dt.to_period("W").apply(lambda p: p.end_time.date().isoformat()))
    out = []
    for (wk, svc), g in res.groupby(["week", "service"]):
        comp = g[g["status"] == "completed"]
        rev = float(comp["price"].sum()) if "price" in comp else 0.0
        out.append({"week_ending": wk, "service": str(svc), "revenue": round(rev, 2),
                    "bookings": int(len(g)),
                    "no_show_rate": round(float((g["status"] == "no_show").mean()) * 100, 1)})
    return out


def _staff_weekly(df):
    if not has_usable_staff(df):
        return []
    comp = df[df["status"] == "completed"].dropna(subset=["date"])
    if "price" in comp:
        comp = comp[comp["price"].notna()]
    if comp.empty:
        return []
    comp = comp.assign(week=comp["date"].dt.to_period("W").apply(lambda p: p.end_time.date().isoformat()))
    out = []
    for (wk, stf), g in comp.groupby(["week", "staff"]):
        out.append({"week_ending": wk, "staff": str(stf),
                    "revenue": round(float(g["price"].sum()), 2), "bookings": int(len(g))})
    return out


def load_service_history(path=BOOKING_HISTORY_DB):
    cols = ["week_ending", "service", "revenue", "bookings", "no_show_rate"]
    if not os.path.exists(path):
        return pd.DataFrame(columns=cols)
    conn = sqlite3.connect(path)
    try:
        h = pd.read_sql_query("SELECT * FROM weekly_service ORDER BY week_ending", conn)
    except Exception:
        h = pd.DataFrame(columns=cols)
    conn.close()
    return h


def load_staff_history(path=BOOKING_HISTORY_DB):
    cols = ["week_ending", "staff", "revenue", "bookings"]
    if not os.path.exists(path):
        return pd.DataFrame(columns=cols)
    conn = sqlite3.connect(path)
    try:
        h = pd.read_sql_query("SELECT * FROM weekly_staff ORDER BY week_ending", conn)
    except Exception:
        h = pd.DataFrame(columns=cols)
    conn.close()
    return h


def monthly_by(hist, dim, value_cols=("revenue", "bookings")):
    """Roll a dimension table (service/staff) up to month x dimension."""
    if hist is None or len(hist) == 0:
        return hist
    h = hist.copy()
    h["month"] = pd.to_datetime(h["week_ending"]).dt.to_period("M").astype(str)
    out = h.groupby(["month", dim])[list(value_cols)].sum().reset_index()
    out["month_label"] = pd.to_datetime(out["month"] + "-01").dt.strftime("%b %Y")
    return out.sort_values(["month", dim]).reset_index(drop=True)
