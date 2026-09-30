"""revenue_core.py — receipts-first revenue engine.

The product is built on the one record every business keeps: receipts (money
taken). The only columns we require are a DATE and an AMOUNT. Everything else —
the service/item, staff, payment method, client — is optional and used when it's
there. Nothing about appointment status, no-shows, or utilisation: this tool
answers "how much am I making, on what, and how is it growing?"
"""
import warnings

import pandas as pd

# Lenient column matching: each canonical field maps from many real-world headers.
COLUMN_ALIASES = {
    "date": ["date", "sale_date", "transaction_date", "txn_date", "paid_at", "created_at",
             "datetime", "appointment_date", "booking_date", "invoice_date"],
    "amount": ["amount", "total", "price", "paid", "sale", "revenue", "net", "gross",
               "subtotal", "total_amount", "amount_paid", "sales", "value"],
    "category": ["category", "service", "item", "product", "service_name", "treatment",
                 "description", "item_name", "type"],
    "staff": ["staff", "employee", "provider", "stylist", "server", "cashier", "staff_member"],
    "payment": ["payment_method", "payment", "method", "tender", "payment_type"],
    "client": ["client", "customer", "client_id", "customer_id", "client_name", "customer_name"],
}
REQUIRED_COLUMNS = ["date", "amount"]


def _norm_key(c):
    return str(c).strip().lower().replace(" ", "_").replace("-", "_")


def _to_dt(series):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pd.to_datetime(series, errors="coerce")


def load_receipts(path):
    return pd.read_csv(path)


def normalize_receipts(df):
    """Map varied headers to a canonical schema, parse date + amount, and drop
    rows that are missing the essentials. Never assumes optional columns exist."""
    df = df.copy()
    keys = {_norm_key(c): c for c in df.columns}
    rename = {}
    for canon, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            k = _norm_key(a)
            if k in keys and keys[k] not in rename.values():
                rename[keys[k]] = canon
                break
    df = df.rename(columns=rename)

    if "amount" in df:
        cleaned = df["amount"].astype(str).str.replace(r"[^0-9.\-]", "", regex=True)
        df["amount"] = pd.to_numeric(cleaned, errors="coerce")
        df = df[df["amount"].notna()]
    if "date" in df:
        df["date"] = _to_dt(df["date"])
        df = df[df["date"].notna()]
        df["month"] = df["date"].dt.to_period("M").astype(str)
        df["weekday"] = df["date"].dt.day_name()
    return df.reset_index(drop=True)


def validate_receipts(df):
    """Required canonical columns still missing ([] = good)."""
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def summary(df):
    rev = float(df["amount"].sum()); n = len(df)
    return {
        "total_revenue": round(rev, 2),
        "sales": n,
        "avg_sale": round(rev / n, 2) if n else 0.0,
        "date_min": df["date"].min().date().isoformat() if "date" in df and n else None,
        "date_max": df["date"].max().date().isoformat() if "date" in df and n else None,
        "categories": int(df["category"].nunique()) if "category" in df else 0,
        "has_category": "category" in df.columns,
        "has_staff": "staff" in df.columns,
    }


def revenue_by_category(df):
    """Where the money comes from. {} when the receipt has no service/item column."""
    if "category" not in df.columns:
        return {}
    total = float(df["amount"].sum()) or 1.0
    res = {}
    for cat, s in df.groupby("category")["amount"]:
        rev = float(s.sum())
        res[str(cat)] = {"revenue": round(rev, 2), "sales": int(len(s)),
                         "avg_sale": round(rev / len(s), 2), "share": round(rev / total * 100, 1)}
    return dict(sorted(res.items(), key=lambda kv: -kv[1]["revenue"]))


def revenue_by_staff(df):
    """Optional: revenue per staff member, when the receipt records who served."""
    if "staff" not in df.columns:
        return {}
    res = {}
    for stf, s in df.groupby("staff")["amount"]:
        res[str(stf)] = {"revenue": round(float(s.sum()), 2), "sales": int(len(s))}
    return dict(sorted(res.items(), key=lambda kv: -kv[1]["revenue"]))
