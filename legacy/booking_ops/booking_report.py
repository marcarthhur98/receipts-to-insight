"""booking_report.py — Weekly Scorecard, analysis-forward.

Leads with the business situation and progress, states findings as observations,
and keeps prescriptions restrained (Worth Your Attention, max 2). The prescriptive
"what to do" coaching lives in the optional AI Advisor (advisor_answer /
generate_booking_brief). Deterministic core; AI is additive and never required.
"""
import os
from datetime import datetime
from booking_health import assess
from booking_sales import compute_sales
from booking_charts import highlight_chart_id
from booking_history import monthly_history
from booking_trends import compute_trends

def _money(v): return f"${v:,.0f}"
def _arrow(d): return "▲" if d > 0 else ("▼" if d < 0 else "—")

def _status(health, areas):
    a = {x["area"] for x in health["act"]}; w = {x["area"] for x in health["watch"]}
    if any(x in a for x in areas): return "🔴"
    if any(x in w for x in areas): return "⚠️"
    return "✅"

def section_verdict(health):
    h = health.get("headline") or {}
    label = "Needs attention" if h.get("state") == "needs_attention" else "On track"
    return f"## Verdict\n\n**{label}** — {h.get('text', '')}"

def section_recognition(health):
    out = []
    if health.get("reward"):
        out.append(f"- ⭐ {health['reward']['message']}")
    if health.get("improved"):
        out.append(f"- 🌱 {health['improved']['message']}")
    return "## Recognition\n\n" + "\n".join(out) if out else ""

def section_whats_happening(health, kpis, sales):
    s = kpis["summary"]; d = health.get("deltas") or {}
    counts = kpis["heatmap"]["counts"]
    busiest = counts.sum(axis=1).idxmax() if not counts.empty else "?"
    quietest = counts.sum(axis=1).idxmin() if not counts.empty else "?"
    r = sales["rankings"]; reb = kpis["rebooking"]["overall_pct"]; idle = kpis["idle"]["idle_share_pct"]
    pulse = f"{_status(health, ['Pulse'])} **Pulse:** {_money(s.get('revenue_completed', 0))} across {s['appointments']:,} appointments"
    if isinstance(d.get("revenue_per_day"), dict):
        rv = d["revenue_per_day"]; pulse += f" ({_arrow(rv['delta'])} {abs(rv['delta'])}/day vs prior)"
    reads = [pulse + "."]
    reads.append(f"{_status(health, ['No-shows', 'Cancellations'])} **Leakage:** {s['no_show_rate']}% no-show, {s['cancellation_rate']}% cancellation.")
    reads.append(f"{_status(health, ['Schedule gaps', 'Utilization'])} **Capacity:** {idle}% idle time; busiest {busiest}, quietest {quietest}.")
    if r.get("top_revenue"):
        mm = f"{_status(health, ['Sales', 'Service yield', 'Service cancellations'])} **Money-makers:** {r['top_revenue']} brings the most revenue"
        if r.get("top_yield"):
            mm += f"; {r['top_yield']} the most per hour"
        reads.append(mm + ".")
    reads.append(f"{_status(health, ['Rebooking'])} **Retention:** {reb}% of clients rebook with the same staff.")
    return "## What's Happening\n\n" + "\n".join(f"- {x}" for x in reads)

def section_attention(health):
    non_chronic = [x for x in health["act"] if not x.get("chronic")]
    chronic = [x for x in health["act"] if x.get("chronic")]
    out = ["## Worth Your Attention", ""]
    if non_chronic:
        for x in non_chronic[:2]:
            out.append(f"- {x['message']}")
            if x.get("action"):
                out.append(f"  - _Suggestion: {x['action']}_")
    else:
        out.append("Nothing needs your attention this period — the situation above is within healthy ranges.")
    if chronic:
        out.append("")
        out.append("_Ongoing (structural, not new this period): " + "; ".join(x["area"] for x in chronic) + "._")
    return "\n".join(out)

def section_trend(health):
    d = health.get("deltas") or {}
    if not any(isinstance(v, dict) for v in d.values()):
        return ""
    labels = {"no_show_rate": "No-show rate (%)", "cancellation_rate": "Cancellation rate (%)",
              "bookings_per_day": "Bookings / day", "revenue_per_day": "Revenue / day ($)"}
    out = ["## Progress vs Prior Period", "",
           f"_Comparing {d.get('prior_range','?')} (prior) to {d.get('recent_range','?')} (recent)._", "",
           "| Metric | Prior | Recent | Change |", "| --- | --- | --- | --- |"]
    for key, label in labels.items():
        if isinstance(d.get(key), dict):
            v = d[key]
            out.append(f"| {label} | {v['prior']} | {v['recent']} | {_arrow(v['delta'])} {abs(v['delta'])} |")
    return "\n".join(out)

def section_history(history):
    if history is None or len(history) < 2:
        return ""
    m = monthly_history(history)
    if len(m) < 1:
        return ""
    out = ["## Progress (month by month)", ""]
    if len(m) >= 2:
        last = m.iloc[-1]; prev = m.iloc[-2]
        d = last["revenue"] - prev["revenue"]
        out.append(f"_{last['month_label']}: {_money(last['revenue'])} revenue "
                   f"({_arrow(d)} {_money(abs(d))} vs {prev['month_label']})._")
        out.append("")
    out += ["| Month | Revenue | Appts | Worked hrs | No-show % |",
            "| --- | --- | --- | --- | --- |"]
    for _, r in m.iterrows():
        out.append(f"| {r['month_label']} | {_money(r['revenue'])} | {int(r['appointments'])} | "
                   f"{r['worked_hours']:.0f} | {r['no_show_rate']}% |")
    return "\n".join(out)

def section_sales(sales):
    bys = sales["by_service"]; r = sales["rankings"]
    if not bys:
        return ""
    out = ["## Sales & Service Mix", ""]
    yph_label = "margin per hour" if sales.get("has_costs") else "revenue per hour"
    tr, ty = r.get("top_revenue"), r.get("top_yield")
    fast, lown, grow = r.get("fastest_growth"), r.get("lowest_noshow"), r.get("best_growth_potential")
    if tr:
        out.append(f"- **Most revenue:** {tr} — ${bys[tr]['revenue']:,.0f} ({bys[tr]['revenue_share']}% of total).")
    if ty:
        note = "" if ty == tr else " — your top-revenue service is not your most time-efficient one"
        out.append(f"- **Most profitable ({yph_label}):** {ty} at ${bys[ty]['revenue_per_hour']}/hr{note}.")
    if fast:
        out.append(f"- **Fastest growing:** {fast} ({bys[fast]['revenue_trend_pct']:+}% revenue vs prior).")
    if lown:
        out.append(f"- **Most reliable (lowest no-show):** {lown} at {bys[lown]['no_show_rate']}%.")
    if grow and "growth_score" in bys.get(grow, {}):
        p = bys[grow]["growth_parts"]
        out.append(f"- **Greatest growth potential:** {grow} (score {bys[grow]['growth_score']} = "
                   f"0.4·trend {p['trend']} + 0.3·yield {p['yield']} + 0.3·reliability {p['reliability']}).")
    out += ["", "| Service | Revenue | Revenue/hr | Trend | No-show |",
            "| --- | --- | --- | --- | --- |"]
    for svc, dd in sorted(bys.items(), key=lambda x: x[1]["revenue"], reverse=True)[:6]:
        out.append(f"| {svc} | ${dd['revenue']:,.0f} | ${dd['revenue_per_hour']} | "
                   f"{dd['revenue_trend_pct']:+}% | {dd['no_show_rate']}% |")
    out.append("")
    out.append("_Revenue/hr = a service's revenue divided by the hours it occupies a chair "
               "(station) — how efficiently it turns booked time into money. Use it to decide what to "
               "promote and which services deserve your scarce peak slots._")
    return "\n".join(out)

def section_kpi_cards(kpis):
    s = kpis["summary"]; idle = kpis["idle"]; reb = kpis["rebooking"]
    rows = [("Appointments", f"{s['appointments']:,}"), ("Date range", f"{s['date_min']} -> {s['date_max']}"),
            ("No-show rate", f"{s['no_show_rate']}%"), ("Cancellation rate", f"{s['cancellation_rate']}%"),
            ("Completed revenue", _money(s.get('revenue_completed', 0))), ("Avg ticket", _money(s.get('avg_ticket', 0))),
            ("Rebooking rate (same staff)", f"{reb['overall_pct']}%"),
            ("Idle time between appts", f"{idle['total_idle_hours']:,.0f} h ({idle['idle_share_pct']}%)")]
    return "\n".join(["## Key Metrics", "", "| Metric | Value |", "| --- | --- |"]
                     + [f"| {k} | {v} |" for k, v in rows])

def section_visuals(charts, highlight=None):
    out = ["## Visual Analysis", ""]
    if not charts:
        out.append("_No charts available._"); return "\n".join(out)
    for c in charts:
        star = " ⭐ (focus this week)" if highlight and c.get("id") == highlight else ""
        out += [f"### {c['title']}{star}", "", f"![{c['title']}]({c['path']})", "", c["description"], ""]
    return "\n".join(out).rstrip()

def build_booking_report(df, kpis, charts=None, health=None, sales=None, history=None,
                         service_history=None, staff_history=None,
                         title="Salon Operations — Weekly Scorecard"):
    if sales is None:
        sales = compute_sales(df)
    if health is None:
        health = assess(df, kpis, sales)
    highlight = highlight_chart_id(health)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    head = [f"# {title}", "", f"_Generated on {ts}_", "",
            "> An analysis of what the data shows this period and how it's changing. Findings come from a "
            "deterministic health-check; prescriptive coaching is available from the optional AI Advisor.",
            "", "---", ""]
    progress = (section_history(history) if (history is not None and len(history) >= 2)
                else section_trend(health))
    trends = compute_trends(history, service_history, staff_history)
    sections = [section_verdict(health), section_recognition(health),
                section_whats_happening(health, kpis, sales), progress,
                section_changing(trends), section_attention(health), section_sales(sales),
                section_kpi_cards(kpis), section_visuals(charts, highlight)]
    return "\n".join(head) + "\n\n".join(s for s in sections if s) + "\n"

def save_report(md, path="outputs/booking_report.md"):
    folder = os.path.dirname(path)
    if folder: os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: f.write(md)
    return path

# ---------------- optional AI Advisor (additive, never required) ----------------
ADVISOR_PLAN_SYSTEM = (
    "You are an operations advisor for a salon/spa. The owner already has a complete, data-derived "
    "scorecard. Turn it into a short prioritised plan: '## Top 3 Opportunities' and '## This Week's Plan' "
    "(3-5 concrete steps). Use only facts in the scorecard. If it says nothing needs attention, say so; "
    "do not invent work."
)
ADVISOR_QA_SYSTEM = (
    "You are an operations advisor for a salon/spa. Answer the owner's question using ONLY the scorecard "
    "provided. Be concise, specific, and practical. If the scorecard doesn't contain the answer, say so "
    "plainly rather than guessing."
)

def _ask_claude(system, user, model=None, max_tokens=700):
    from ai_summary import load_api_key, DEFAULT_MODEL
    import anthropic
    client = anthropic.Anthropic(api_key=load_api_key())
    msg = client.messages.create(model=model or DEFAULT_MODEL, max_tokens=max_tokens,
                                 system=system, messages=[{"role": "user", "content": user}])
    return "\n".join(b.text for b in msg.content if hasattr(b, "text")).strip()

def generate_booking_brief(report_markdown, model=None):
    return _ask_claude(ADVISOR_PLAN_SYSTEM, "Scorecard:\n\n" + report_markdown, model, 800)

def advisor_answer(question, report_markdown, model=None):
    return _ask_claude(ADVISOR_QA_SYSTEM,
                       f"Scorecard:\n\n{report_markdown}\n\nQuestion: {question}", model, 600)


def section_changing(trends):
    if not trends:
        return ""
    pv = trends.get("price_volume"); dr = trends.get("drivers")
    lk = trends.get("leakage"); pw = trends.get("provider_watch")
    if not pv and not dr:
        return ""
    out = ["## What's Changing & Why", ""]
    if pv:
        if pv["driver"] == "volume":
            detail = "more bookings" if pv["volume_effect"] >= 0 else "fewer bookings"
        else:
            detail = "a higher average ticket" if pv["price_effect"] >= 0 else "a lower average ticket"
        out.append(f"- Revenue {_arrow(pv['rev_change'])} ${abs(pv['rev_change']):,.0f} from "
                   f"{pv['prev_label']} to {pv['last_label']}, driven mainly by {detail}.")
    if dr and dr.get("up"):
        out.append("- Gainers: " + ", ".join(f"{s} +${d:,.0f}" for s, d in dr["up"]) + ".")
    if dr and dr.get("down"):
        out.append("- Decliners: " + ", ".join(f"{s} −${abs(d):,.0f}" for s, d in dr["down"]) + ".")
    if lk:
        out.append(f"- No-shows {_arrow(lk['delta'])} {abs(lk['delta'])} pts ({lk['prev']}% → {lk['last']}%).")
    if pw:
        out.append(f"- ⚠️ {pw['staff']}'s revenue fell ${abs(pw['delta']):,.0f} "
                   f"({pw['prev_label']} → {pw['last_label']}) — worth a check.")
    return "\n".join(out)
