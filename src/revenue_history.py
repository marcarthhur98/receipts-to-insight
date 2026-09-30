"""revenue_history.py — local monthly revenue store (SQLite).

Each run upserts one row per month (revenue + number of sales) keyed by month,
so the timeline self-corrects across uploads and builds a true month-by-month
history the business can watch grow. Thin interface; swappable for a cloud DB
later without touching the rest of the app.
"""
import os
import sqlite3
from datetime import datetime

import pandas as pd

DB_DEFAULT = "outputs/revenue_history.db"
ARCHIVE_DEFAULT = "data/archive"
COLUMNS = ["month", "revenue", "sales"]


def archive_upload(df, source_name="receipts", folder=ARCHIVE_DEFAULT):
    """Keep a timestamped copy of every analysed file, so there's always an
    audit trail and the history can be rebuilt from source. Returns the path
    written (or None if it couldn't be saved — archiving must never block a run)."""
    try:
        os.makedirs(folder, exist_ok=True)
        stem = os.path.splitext(os.path.basename(str(source_name)))[0] or "receipts"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(folder, f"{stem}_{stamp}.csv")
        df.to_csv(path, index=False)
        return path
    except Exception:
        return None


def _monthly(df):
    return [{"month": m, "revenue": round(float(s.sum()), 2), "sales": int(len(s))}
            for m, s in df.groupby("month")["amount"]]


def init_db(path=DB_DEFAULT):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE IF NOT EXISTS monthly (
        month TEXT PRIMARY KEY, revenue REAL, sales INTEGER, updated_at TEXT)""")
    return conn


def save_snapshot(df, path=DB_DEFAULT):
    conn = init_db(path)
    now = datetime.now().isoformat(timespec="seconds")
    for r in _monthly(df):
        conn.execute("INSERT OR REPLACE INTO monthly (month, revenue, sales, updated_at) "
                     "VALUES (?,?,?,?)", (r["month"], r["revenue"], r["sales"], now))
    conn.commit(); conn.close()
    return path


def load_history(path=DB_DEFAULT):
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)
    conn = sqlite3.connect(path)
    try:
        h = pd.read_sql_query("SELECT month, revenue, sales FROM monthly ORDER BY month", conn)
    except Exception:
        h = pd.DataFrame(columns=COLUMNS)
    conn.close()
    if len(h):
        h["month_label"] = pd.to_datetime(h["month"] + "-01").dt.strftime("%b %Y")
        h["avg_sale"] = (h["revenue"] / h["sales"].replace(0, 1)).round(2)
    return h
