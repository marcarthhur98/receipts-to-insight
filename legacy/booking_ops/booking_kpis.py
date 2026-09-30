"""booking_kpis.py — booking analytics engine (KPIs with confidence gating)."""
import warnings

import pandas as pd


def _to_dt(series):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pd.to_datetime(series, errors="coerce")

OPEN_HOUR, CLOSE_HOUR = 9, 19
OPEN_HOURS = CLOSE_HOUR - OPEN_HOUR
from booking_config import MIN_SUPPORT  # central tunable

COLUMN_ALIASES = {
    "appointment_id": ["appointment_id","appt_id","booking_id","id"],
    "client_id": ["client_id","customer_id","client"],
    "service": ["service","service_name","treatment"],
    "staff": ["staff","staff_member","employee","stylist","practitioner","provider"],
    "date": ["date","appointment_date","appt_date"],
    "start_time": ["start_time","start","time"],
    "end_time": ["end_time","end"],
    "duration_min": ["duration_min","duration","length_min"],
    "price": ["price","amount","cost","total"],
    "status": ["status","appointment_status","appt_status","booking_status","state","outcome"],
    "booking_source": ["booking_source","source","channel"],
    "booked_at": ["booked_at","created_at","booking_created"],
    "cancel_lead_hours": ["cancel_lead_hours","cancellation_lead_hours"],
}

STATUS_MAP = {
    "completed":"completed","complete":"completed","done":"completed","attended":"completed","showed":"completed",
    "cancelled":"cancelled","canceled":"cancelled","cancel":"cancelled",
    "no-show":"no_show","no show":"no_show","noshow":"no_show","no_show":"no_show","did not arrive":"no_show",
    "booked":"booked","scheduled":"booked","upcoming":"booked","confirmed":"booked","pending":"booked",
}

def load_bookings(path):
    return pd.read_csv(path)

def _norm_key(c):
    """Normalise a column name for matching: lowercase, spaces/hyphens -> underscores."""
    return str(c).strip().lower().replace(" ", "_").replace("-", "_")


def _map_status(v):
    """Map a messy status value to completed / cancelled / no_show / booked."""
    v = str(v).strip().lower()
    if v in STATUS_MAP:
        return STATUS_MAP[v]
    if "noshow" in v or ("no" in v and "show" in v):
        return "no_show"
    if "cancel" in v:
        return "cancelled"
    if any(w in v for w in ("complete", "attended", "fulfilled", "checked", "paid", "done", "showed")):
        return "completed"
    if any(w in v for w in ("book", "schedul", "confirm", "upcoming", "pending")):
        return "booked"
    return v


def normalize_bookings(df):
    """Map varied column names to a canonical schema (lenient on case/spacing) and
    derive helper fields. Never assumes a column exists — use validate_bookings()
    to check for the few that are required before analysing."""
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

    if "status" in df:
        df["status"] = df["status"].map(_map_status)
    if "date" in df:
        df["date"] = _to_dt(df["date"])
        df["weekday"] = df["date"].dt.day_name()
    if "start_time" in df:
        parsed = _to_dt(df["start_time"])
        df["hour"] = parsed.dt.hour
    if "duration_min" not in df and {"start_time", "end_time"}.issubset(df.columns):
        s = _to_dt(df["start_time"])
        e = _to_dt(df["end_time"])
        df["duration_min"] = (e - s).dt.total_seconds() / 60
    if "price" in df:
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
    return df


REQUIRED_COLUMNS = ["status", "date"]


def validate_bookings(df):
    """Return the required canonical columns still missing after normalization
    ([] = good). Lets the app show a clear message instead of crashing."""
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]

# -------- helper masks --------
def inferred_day_length(df):
    """Length of the salon's working day, inferred from observed booking times."""
    occ = df.dropna(subset=["hour", "duration_min"])
    if occ.empty:
        return OPEN_HOURS
    open_h = float(occ["hour"].min())
    close_h = float((occ["hour"] + occ["duration_min"] / 60).max())
    return max(close_h - open_h, 1.0)

def _resolved(df):     # past appts with a known outcome
    return df[df["status"].isin(["completed","cancelled","no_show"])]
def _completed(df):
    return df[df["status"] == "completed"]

# -------- KPIs --------
def summary_kpis(df):
    resolved = _resolved(df); completed = _completed(df)
    n = len(df)
    out = {
        "appointments": n,
        "date_min": df["date"].min().date().isoformat() if "date" in df else None,
        "date_max": df["date"].max().date().isoformat() if "date" in df else None,
        "clients": int(df["client_id"].nunique()) if "client_id" in df else None,
        "completed": int((df["status"]=="completed").sum()),
        "no_show_rate": round((resolved["status"]=="no_show").mean()*100,1) if len(resolved) else 0,
        "cancellation_rate": round((resolved["status"]=="cancelled").mean()*100,1) if len(resolved) else 0,
        "future_booked": int((df["status"]=="booked").sum()),
    }
    if "price" in df:
        out["revenue_completed"] = round(float(completed["price"].sum()), 2)
        out["avg_ticket"] = round(float(completed["price"].mean()), 2) if len(completed) else 0
    return out

def rate_by(df, dim, outcome):
    """Rate of `outcome` by dimension, with support count and confidence flag."""
    if dim not in df.columns:
        return {}
    resolved = _resolved(df)
    g = resolved.groupby(dim)["status"]
    res = {}
    for key, s in g:
        n = len(s)
        rate = round(float((s == outcome).mean())*100, 1)
        res[str(key)] = {"rate": rate, "n": int(n), "confident": n >= MIN_SUPPORT}
    return dict(sorted(res.items(), key=lambda kv: kv[1]["rate"], reverse=True))

def utilization_by_staff(df):
    """Realized utilization: completed booked hours vs an inferred full day per active day.
    Staff with fewer than MIN_SUPPORT completed appts are excluded (too little data)."""
    if "staff" not in df.columns or "duration_min" not in df.columns:
        return {}
    completed = _completed(df)
    day_len = inferred_day_length(df)
    res = {}
    for staff, g in completed.groupby("staff"):
        if len(g) < MIN_SUPPORT:
            continue
        booked_h = g["duration_min"].sum() / 60
        active_days = g["date"].dt.date.nunique()
        capacity_h = active_days * day_len
        util = round(booked_h / capacity_h * 100, 1) if capacity_h else 0
        rev = float(g["price"].sum()) if "price" in g else 0
        res[staff] = {
            "booked_hours": round(booked_h, 1),
            "active_days": int(active_days),
            "utilization_pct": util,
            "revenue": round(rev, 2),
            "revenue_per_available_hour": round(rev / capacity_h, 2) if capacity_h else 0,
        }
    return dict(sorted(res.items(), key=lambda kv: kv[1]["utilization_pct"], reverse=True))

def rebooking_rate(df):
    """Share of completed appts whose client has a later appt. Overall and by staff."""
    if "client_id" not in df.columns or "staff" not in df.columns:
        return {"overall_pct": 0, "by_staff": {}}
    df = df.sort_values("date")
    completed = _completed(df).copy()
    # Stickiness: does the client return TO THE SAME STAFF after this visit?
    last_cs = df.groupby(["client_id", "staff"])["date"].max()
    def _returned(r):
        m = last_cs.get((r["client_id"], r["staff"]))
        return bool(m is not None and m > r["date"])
    completed["has_later"] = completed.apply(_returned, axis=1)
    overall = round(float(completed["has_later"].mean())*100, 1) if len(completed) else 0
    by_staff = {}
    for staff, g in completed.groupby("staff"):
        if len(g) < MIN_SUPPORT:
            continue
        by_staff[staff] = {"rebooking_pct": round(float(g["has_later"].mean())*100, 1), "n": int(len(g))}
    by_staff = dict(sorted(by_staff.items(), key=lambda kv: kv[1]["rebooking_pct"], reverse=True))
    return {"overall_pct": overall, "by_staff": by_staff}

def idle_gaps(df):
    """Idle minutes = staff present-span minus booked time, per staff-day. Aggregated."""
    if not {"hour", "duration_min", "staff"}.issubset(df.columns):
        return {"total_idle_hours": 0, "idle_share_pct": 0, "idle_share_by_weekday": {}}
    occ = df[df["status"].isin(["completed","booked","no_show"])].dropna(subset=["hour","duration_min"])
    total_idle = 0.0; total_present = 0.0
    wd_idle = {}; wd_present = {}
    for (staff, day), g in occ.groupby(["staff", occ["date"].dt.date]):
        first = float((g["hour"]*60).min())
        last = float((g["hour"]*60 + g["duration_min"]).max())
        present = last - first
        booked = float(g["duration_min"].sum())
        idle = max(present - booked, 0)
        total_idle += idle; total_present += present
        wd = pd.Timestamp(day).day_name()
        wd_idle[wd] = wd_idle.get(wd, 0) + idle
        wd_present[wd] = wd_present.get(wd, 0) + present
    share_by_wd = {wd: round(wd_idle[wd]/wd_present[wd]*100, 1) for wd in wd_idle if wd_present[wd]}
    share_by_wd = dict(sorted(share_by_wd.items(), key=lambda kv: kv[1], reverse=True))
    return {"total_idle_hours": round(total_idle/60, 1),
            "idle_share_pct": round(total_idle/total_present*100, 1) if total_present else 0,
            "idle_share_by_weekday": share_by_wd}

def demand_heatmap(df):
    """Counts and no-show rate by weekday x hour for the signature heatmap."""
    order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    empty = pd.DataFrame()
    if "hour" not in df.columns or "weekday" not in df.columns:
        return {"counts": empty, "noshow_rate": empty}
    occ = df.dropna(subset=["hour"]).assign(_n=1)
    if occ.empty:
        return {"counts": empty, "noshow_rate": empty}
    counts = occ.pivot_table(index="weekday", columns="hour", values="_n",
                             aggfunc="count", fill_value=0)
    resolved = _resolved(occ)
    if len(resolved):
        ns = resolved.assign(ns=resolved["status"].eq("no_show")).pivot_table(
            index="weekday", columns="hour", values="ns", aggfunc="mean", fill_value=0)
        ns = ns.reindex([d for d in order if d in ns.index])
    else:
        ns = empty
    counts = counts.reindex([d for d in order if d in counts.index])
    return {"counts": counts, "noshow_rate": ns}

def compute_all(df):
    return {
        "summary": summary_kpis(df),
        "noshow_by_source": rate_by(df, "booking_source", "no_show") if "booking_source" in df else {},
        "noshow_by_weekday": rate_by(df, "weekday", "no_show"),
        "noshow_by_hour": rate_by(df, "hour", "no_show"),
        "cancel_by_service": rate_by(df, "service", "cancelled"),
        "utilization": utilization_by_staff(df),
        "rebooking": rebooking_rate(df),
        "idle": idle_gaps(df),
        "heatmap": demand_heatmap(df),
    }
