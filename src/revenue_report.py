"""revenue_report.py — the plain markdown revenue summary (Overview / Growth /
Breakdown). Descriptive only: how much you make and how it's changing. An
optional AI recap can be appended; it never prescribes actions.
"""
import os
from datetime import datetime

from revenue_core import summary, revenue_by_category
from revenue_trends import (growth_summary, price_volume, category_drivers,
                            annual_summary, same_month_last_year, trailing_12,
                            year_in_review)

def _money(v): return f"${v:,.0f}"
def _arrow(d): return "▲" if d > 0 else ("▼" if d < 0 else "—")
def _yoy(pct): return "first year on record" if pct is None else f"{_arrow(pct)} {abs(pct)}% vs the year before"


def build_report(df, history=None, charts=None, title="Revenue Summary"):
    s = summary(df)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    out = [f"# {title}", "", f"_Generated on {ts}_", "", "---", ""]

    out += ["## Overview", "",
            f"- **Total revenue:** {_money(s['total_revenue'])}",
            f"- **Sales:** {s['sales']:,}",
            f"- **Average sale:** {_money(s['avg_sale'])}",
            f"- **Period:** {s['date_min']} → {s['date_max']}"]

    g = growth_summary(history); pv = price_volume(history); dr = category_drivers(df)
    if g:
        out += ["", "## Growth", "",
                f"- **{g['last_label']}:** {_money(g['last_revenue'])} "
                f"({_arrow(g['rev_change'])} {abs(g['pct'])}% vs {g['prev_label']}).",
                f"- Best month: {g['best_label']} ({_money(g['best_revenue'])}); "
                f"weakest: {g['worst_label']} ({_money(g['worst_revenue'])}). "
                f"{g['months_tracked']} months tracked."]
        if pv:
            if pv["driver"] == "flat":
                out.append("- Revenue was roughly flat versus the prior month.")
            else:
                detail = (("more sales" if pv["volume_effect"] >= 0 else "fewer sales")
                          if pv["driver"] == "volume"
                          else ("a higher average sale" if pv["price_effect"] >= 0 else "a lower average sale"))
                out.append(f"- The latest change was driven mainly by {detail}.")
                out.append(
                    f"  - Breakdown: {_arrow(pv['volume_effect'])} {_money(abs(pv['volume_effect']))} from volume, "
                    f"{_arrow(pv['price_effect'])} {_money(abs(pv['price_effect']))} from average sale "
                    f"(net {_arrow(pv['total_change'])} {_money(abs(pv['total_change']))}).")
        if dr and (dr["up"] or dr["down"]):
            if dr["up"]:
                out.append("- Gained: " + ", ".join(f"{c} +{_money(v)}" for c, v in dr["up"]) + ".")
            if dr["down"]:
                out.append("- Slipped: " + ", ".join(f"{c} −{_money(abs(v))}" for c, v in dr["down"]) + ".")

    bc = revenue_by_category(df)
    if bc:
        out += ["", "## Where your money comes from", "",
                "| Service | Revenue | Share | Sales | Avg sale |",
                "| --- | --- | --- | --- | --- |"]
        for c, d in list(bc.items())[:10]:
            out.append(f"| {c} | {_money(d['revenue'])} | {d['share']}% | {d['sales']:,} | {_money(d['avg_sale'])} |")

    if charts:
        out += ["", "## Charts", ""]
        for c in charts:
            out += [f"### {c['title']}", "", f"![{c['title']}]({c['path']})", "", c["description"], ""]
    return "\n".join(out).rstrip() + "\n"


def build_year_review(history, df=None, year=None, charts=None):
    """A standalone 'Year in Review' summary: the annual headline, how it compares
    to prior years, the highs and lows, and where the year's money came from.
    Descriptive only. Returns '' when there isn't enough history yet."""
    review = year_in_review(history, df, year)
    if not review:
        return ""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    out = [f"# {review['year']} — Year in Review", "", f"_Generated on {ts}_", "", "---", "",
           "## The headline", "",
           f"- **Total earned in {review['year']}:** {_money(review['revenue'])} "
           f"({_yoy(review['yoy_pct'])}).",
           f"- **Sales:** {review['sales']:,} over {review['months']} month(s); "
           f"average sale {_money(review['avg_sale'])}.",
           f"- **Best month:** {review['best_label']} ({_money(review['best_revenue'])}). "
           f"**Quietest:** {review['worst_label']} ({_money(review['worst_revenue'])})."]

    sm = same_month_last_year(history)
    if sm and sm["label"].endswith(review["year"]):
        out.append(f"- **{sm['label']} vs {sm['prior_label']}:** {_money(sm['revenue'])} "
                   f"({_yoy(sm['pct'])}) — a like-for-like, season-matched comparison.")

    years = annual_summary(history)
    if len(years) >= 2:
        out += ["", "## Year by year", "", "| Year | Revenue | Sales | Avg sale | Growth |",
                "| --- | --- | --- | --- | --- |"]
        for r in years:
            g = "—" if r["yoy_pct"] is None else f"{_arrow(r['yoy_pct'])} {abs(r['yoy_pct'])}%"
            out.append(f"| {r['year']} | {_money(r['revenue'])} | {r['sales']:,} | "
                       f"{_money(r['avg_sale'])} | {g} |")

    if review["top_services"]:
        out += ["", f"## Where {review['year']}'s money came from", "",
                "| Service | Revenue |", "| --- | --- |"]
        for name, rev in review["top_services"]:
            out.append(f"| {name} | {_money(rev)} |")

    if charts:
        out += ["", "## Charts", ""]
        for c in charts:
            out += [f"### {c['title']}", "", f"![{c['title']}]({c['path']})", "", c["description"], ""]
    return "\n".join(out).rstrip() + "\n"


def save_report(md, path="outputs/revenue_report.md"):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path


# ---------------- optional, descriptive AI recap (never prescriptive) ----------------
RECAP_SYSTEM = (
    "You are a friendly bookkeeper summarising a small business's revenue for the owner. "
    "Write 3-4 plain sentences describing how much they made and how it's changing, using ONLY "
    "the figures in the summary. Be encouraging and factual. Do NOT give advice or tell them what "
    "to do — just describe the numbers."
)


def generate_recap(report_markdown, model=None):
    from ai_summary import load_api_key, DEFAULT_MODEL
    import anthropic
    client = anthropic.Anthropic(api_key=load_api_key())
    msg = client.messages.create(model=model or DEFAULT_MODEL, max_tokens=400, system=RECAP_SYSTEM,
                                 messages=[{"role": "user", "content": report_markdown}])
    return "\n".join(b.text for b in msg.content if hasattr(b, "text")).strip()
