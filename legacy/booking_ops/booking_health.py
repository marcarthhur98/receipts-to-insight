"""booking_health.py — deterministic health-check, benchmarks, deltas, verdict.

This is the honesty layer. It decides whether the business is operating well and
only surfaces an action when a metric is BOTH reliably measured (enough data) and
MATERIALLY off (a large enough gap to matter). If everything is within healthy
ranges it says so — "no action needed" is a valid output. No AI is involved here;
this stands entirely on its own.
"""
from booking_kpis import MIN_SUPPORT, _resolved
from booking_config import (NOSHOW_WATCH, NOSHOW_ACT, CANCEL_WATCH, CANCEL_ACT,
                            IDLE_WATCH, IDLE_ACT, UTIL_LOW, EFF_CANCEL_SVC, EFF_UTIL,
                            EFF_REBOOK, EFF_NOSHOW_SRC, STAR_W_UTIL, STAR_W_REBOOK,
                            STAR_W_YIELD, IMPROVED_MIN_PER_PERIOD, IMPROVED_MIN_PCT,
                            PRIME_GAP_WATCH, PRIME_GAP_ACT, CHRONIC_AREAS)


def _rate(series, outcome):
    return round(float((series == outcome).mean()) * 100, 1) if len(series) else 0.0


def period_deltas(df):
    """Compare the recent half of the data to the prior half (same file)."""
    r = _resolved(df).dropna(subset=["date"])
    if r["date"].nunique() < 4:
        return {}
    lo, hi = r["date"].min(), r["date"].max()
    cutoff = lo + (hi - lo) / 2
    prior, recent = r[r["date"] <= cutoff], r[r["date"] > cutoff]
    if len(prior) < MIN_SUPPORT or len(recent) < MIN_SUPPORT:
        return {}

    def block(x):
        comp = x[x["status"] == "completed"]
        days = x["date"].dt.date.nunique() or 1
        return {
            "no_show_rate": _rate(x["status"], "no_show"),
            "cancellation_rate": _rate(x["status"], "cancelled"),
            "bookings_per_day": round(len(x) / days, 1),
            "revenue_per_day": round(float(comp["price"].sum()) / days, 0) if "price" in x else 0,
        }

    p, c = block(prior), block(recent)
    out = {"prior_range": f"{prior['date'].min().date()} – {prior['date'].max().date()}",
           "recent_range": f"{recent['date'].min().date()} – {recent['date'].max().date()}"}
    for key in p:
        out[key] = {"prior": p[key], "recent": c[key], "delta": round(c[key] - p[key], 1)}
    return out


def _noshow_focus(kpis):
    """Where no-shows concentrate (only differences large enough to matter)."""
    bits = []
    src = {k: v for k, v in (kpis.get("noshow_by_source") or {}).items() if v["n"] >= MIN_SUPPORT}
    if len(src) >= 2:
        worst, best = next(iter(src.items())), list(src.items())[-1]
        if worst[1]["rate"] - best[1]["rate"] >= EFF_NOSHOW_SRC:
            bits.append(f"{worst[0]} bookings ({worst[1]['rate']}%)")
    by_hour = kpis.get("noshow_by_hour") or {}
    ev_n = ev_x = day_n = day_x = 0
    for h, d in by_hour.items():
        H = int(h); n = d["n"]; f = d["rate"]/100 * n
        if H >= 17: ev_n += n; ev_x += f
        else: day_n += n; day_x += f
    if ev_n and day_n and (ev_x/ev_n*100 - day_x/day_n*100) >= EFF_NOSHOW_SRC:
        bits.append(f"evening slots ({ev_x/ev_n*100:.0f}%)")
    return bits


def _star_performer(kpis):
    """Transparent staff score: equal blend of utilisation, rebooking, and
    revenue per available hour (each normalised to the team's best). Gated."""
    util = kpis["utilization"]; reb = kpis["rebooking"]["by_staff"]
    staff = [s for s in util if s in reb]
    if len(staff) < 2:
        return None
    max_u = max(util[s]["utilization_pct"] for s in staff) or 1
    max_r = max(reb[s]["rebooking_pct"] for s in staff) or 1
    max_y = max(util[s]["revenue_per_available_hour"] for s in staff) or 1
    best, best_score, parts = None, -1.0, None
    for s in staff:
        u = util[s]["utilization_pct"] / max_u
        r = reb[s]["rebooking_pct"] / max_r
        y = util[s]["revenue_per_available_hour"] / max_y
        score = round(STAR_W_UTIL * u + STAR_W_REBOOK * r + STAR_W_YIELD * y, 3)
        if score > best_score:
            best, best_score = s, score
            parts = {"utilization": round(u, 2), "rebooking": round(r, 2), "yield": round(y, 2)}
    return {"staff": best, "score": best_score, "parts": parts,
            "util": util[best]["utilization_pct"], "rebooking": reb[best]["rebooking_pct"],
            "rev_per_hour": util[best]["revenue_per_available_hour"],
            "message": (f"Reward {best} — your top performer this period (best blend of utilisation, "
                        f"rebooking, and revenue per hour). A bonus or a public shout-out keeps it up.")}


def _most_improved(df, exclude=None):
    """Recognise the staff member whose completed revenue rose most, recent vs prior
    half-period. Gated by appointment volume in both halves; excludes the star so
    recognition rotates."""
    if "staff" not in df.columns or "price" not in df.columns:
        return None
    c = df[df["status"] == "completed"].dropna(subset=["date"])
    if "price" in c:
        c = c[c["price"].notna()]
    if c["date"].nunique() < 4:
        return None
    lo, hi = c["date"].min(), c["date"].max()
    cut = lo + (hi - lo) / 2
    prior, recent = c[c["date"] <= cut], c[c["date"] > cut]
    best, best_pct = None, IMPROVED_MIN_PCT
    for staff in set(c["staff"].dropna()):
        if staff == exclude:
            continue
        gp, gr = prior[prior["staff"] == staff], recent[recent["staff"] == staff]
        if len(gp) < IMPROVED_MIN_PER_PERIOD or len(gr) < IMPROVED_MIN_PER_PERIOD:
            continue
        pr = float(gp["price"].sum())
        if pr <= 0:
            continue
        pct = (float(gr["price"].sum()) - pr) / pr * 100
        if pct > best_pct:
            best, best_pct = staff, pct
    if best is None:
        return None
    return {"staff": best, "pct": round(best_pct, 1),
            "message": f"Recognise {best} — most improved this period (completed revenue up "
                       f"{round(best_pct, 1)}% vs the prior period)."}


def _positive_line(deltas):
    d = deltas or {}
    rv = d.get("revenue_per_day")
    if isinstance(rv, dict) and rv["delta"] > 0:
        return f"revenue up ${abs(rv['delta']):,.0f}/day vs the prior period"
    ns = d.get("no_show_rate")
    if isinstance(ns, dict) and ns["delta"] < 0:
        return f"no-shows down {abs(ns['delta'])} pts vs the prior period"
    return "all tracked metrics are within a healthy range"


def assess(df, kpis, sales=None):
    """Return {deltas, verdict, act, watch, healthy}. Each item: {area, message, action}."""
    act, watch, healthy = [], [], []

    def add(bucket, area, message, action=None):
        bucket.append({"area": area, "message": message, "action": action})

    # --- No-shows (absolute guardrail + where they concentrate) ---
    ns = kpis["summary"]["no_show_rate"]; focus = _noshow_focus(kpis)
    foc = (" Concentrated in " + ", ".join(focus) + ".") if focus else ""
    if ns >= NOSHOW_ACT:
        add(act, "No-shows", f"No-show rate is **{ns}%**, above the {NOSHOW_ACT}% action line.{foc}",
            "Require deposits or confirmations for the riskiest bookings"
            + (f" ({', '.join(focus)})" if focus else "") + ".")
    elif ns >= NOSHOW_WATCH:
        add(watch, "No-shows", f"No-show rate is **{ns}%** (watch band {NOSHOW_WATCH}–{NOSHOW_ACT}%).{foc}")
    else:
        add(healthy, "No-shows", f"No-show rate {ns}% is within a healthy range.")

    # --- Cancellations overall ---
    cr = kpis["summary"]["cancellation_rate"]
    if cr >= CANCEL_ACT:
        add(act, "Cancellations", f"Cancellation rate is **{cr}%**, above the {CANCEL_ACT}% line.",
            "Introduce deposits or card-on-file at booking.")
    elif cr >= CANCEL_WATCH:
        add(watch, "Cancellations", f"Cancellation rate is **{cr}%** (watch band).")
    else:
        add(healthy, "Cancellations", f"Overall cancellation rate {cr}% is healthy.")

    # --- Cancellations by service (relative to own average, supported) ---
    svc = {k: v for k, v in kpis["cancel_by_service"].items() if v["n"] >= MIN_SUPPORT}
    flagged = [(k, v["rate"]) for k, v in svc.items() if v["rate"] >= cr + EFF_CANCEL_SVC]
    if flagged:
        names = ", ".join(f"{k} ({r}%)" for k, r in flagged[:3])
        add(act, "Service cancellations",
            f"These services cancel well above your {cr}% average: {names}.",
            f"Require a deposit for {', '.join(k for k, _ in flagged[:2])}.")

    # --- Utilization (relative laggard AND absolutely low) ---
    u = kpis["utilization"]
    if len(u) >= 2:
        avg = sum(d["utilization_pct"] for d in u.values()) / len(u)
        worst = min(u, key=lambda s: u[s]["utilization_pct"]); wv = u[worst]["utilization_pct"]
        if wv <= avg - EFF_UTIL and wv < UTIL_LOW:
            add(act, "Utilization", f"**{worst}** is well below the team ({wv}% vs {avg:.0f}% average).",
                f"Fill {worst}'s calendar — promote their services or rebalance hours to busier days.")
        else:
            add(healthy, "Utilization", "Staff utilisation is reasonably balanced.")

    # --- Rebooking (relative to salon-wide, supported) ---
    rb = kpis["rebooking"]["by_staff"]; overall = kpis["rebooking"]["overall_pct"]
    if len(rb) >= 2:
        worst = min(rb, key=lambda s: rb[s]["rebooking_pct"]); wv = rb[worst]["rebooking_pct"]
        if wv <= overall - EFF_REBOOK:
            add(act, "Rebooking", f"**{worst}** retains fewer clients ({wv}% vs {overall}% salon-wide).",
                f"Add a book-your-next-visit prompt at checkout and coach {worst} on rebooking.")
        else:
            add(healthy, "Rebooking", "Client rebooking is consistent across staff.")

    # --- Schedule gaps ---
    idle = kpis["idle"]["idle_share_pct"]
    if idle >= IDLE_ACT:
        add(act, "Schedule gaps", f"About **{idle}%** of staff time sits idle between appointments.",
            "Tighten the booking grid — cluster appointments and consolidate the quietest windows.")
    elif idle >= IDLE_WATCH:
        add(watch, "Schedule gaps", f"Idle time between appointments is **{idle}%** (watch).")
    else:
        add(healthy, "Schedule gaps", f"Idle time between appointments ({idle}%) is under control.")

    # --- Sales & service mix (only when meaningful) ---
    if sales and sales.get("by_service"):
        bys = sales["by_service"]; ranks = sales["rankings"]
        ty = ranks.get("top_yield")
        if ty and bys[ty].get("confident") and bys[ty]["revenue_share"] < 15:
            add(act, "Service yield",
                f"**{ty}** earns the most per chair-hour (${bys[ty]['revenue_per_hour']}/hr) "
                f"but is only {bys[ty]['revenue_share']}% of revenue.",
                f"Promote {ty} and steer demand toward it — it is your most time-efficient service.")
        fg = ranks.get("fastest_growth")
        if fg and bys[fg].get("confident") and bys[fg]["revenue_trend_pct"] >= 20:
            add(watch, "Service growth",
                f"**{fg}** revenue is up {bys[fg]['revenue_trend_pct']}% vs the prior period — protect its capacity.")
        tr = ranks.get("top_revenue")
        if tr and bys[tr]["revenue_share"] >= 40:
            add(watch, "Revenue concentration",
                f"**{tr}** is {bys[tr]['revenue_share']}% of revenue — a lot riding on one service.")
        pt = sales.get("prime_time")
        if pt and pt.get("promote") and pt.get("move"):
            if pt["gap"] >= PRIME_GAP_ACT:
                add(act, "Prime-time yield",
                    f"Your busiest hours yield ${pt['prime_yield']}/hr vs ${pt['overall_yield']}/hr overall.",
                    f"Steer {pt['promote']} into peak slots and move {pt['move']} to quieter times.")
            elif pt["gap"] >= PRIME_GAP_WATCH:
                add(watch, "Prime-time yield",
                    f"Busiest hours yield ${pt['prime_yield']}/hr, a bit below the ${pt['overall_yield']}/hr average.")
            else:
                add(healthy, "Prime-time yield", "Your busiest hours are filled with high-yield services.")

    for x in act:
        x["chronic"] = x["area"] in CHRONIC_AREAS
    non_chronic = [x for x in act if not x["chronic"]]
    deltas = period_deltas(df)
    state = "needs_attention" if non_chronic else "on_track"
    top_priority = non_chronic[0] if non_chronic else None
    headline_text = top_priority["action"] if state == "needs_attention" else _positive_line(deltas)
    headline = {"state": state, "top_priority": top_priority, "text": headline_text}
    verdict = (("Needs attention — " + headline_text) if state == "needs_attention"
               else ("On track — " + headline_text))

    reward = _star_performer(kpis)
    improved = _most_improved(df, exclude=reward["staff"] if reward else None)
    return {"deltas": deltas, "verdict": verdict, "headline": headline, "act": act, "watch": watch,
            "healthy": healthy, "reward": reward, "improved": improved}
