# Revenue & Growth

A simple revenue tracker for small and mid-sized businesses. Upload your
receipts (a sales/transactions export) and the tool tells you **how much you
make**, **where the money comes from**, and **how you're growing** — month by
month.

It's built on the one record every business actually keeps: receipts. The only
things it needs are a **date** and an **amount** per sale. There's no
appointment-status tracking, no no-show or utilisation maths, and no list of
things you "must do" — just a clear, honest picture of your money.

## What it shows

- **Overview** — total revenue, number of sales, average sale.
- **Where the money comes from** — revenue per service/item (when your export
  has a service column), so you can see what earns most.
- **Growth** — a month-by-month revenue timeline, the latest change vs the prior
  month, your best and weakest months, and a plain read of whether a change came
  from *more sales* (volume) or a *higher average sale* (price).
- **Year** — the yearly perspective: revenue per calendar year with
  year-over-year growth, a trailing-12-months figure, a season-matched
  *same-month-last-year* comparison, and a downloadable **Year-in-Review**
  (best/worst months, top services, year-by-year table).
- **Optional plain-English summary** — a short, friendly recap written by Claude.
  Off by default, needs an API key, and is purely descriptive (it never tells you
  what to do).

History is stored locally in a small SQLite file, so each upload adds to your
timeline and the picture builds over time. Every file you analyse is also copied
to `data/archive/` with a timestamp — an audit trail you can always rebuild from.

## The data you need

A CSV export of your sales. Column names are matched leniently, so most receipt
or point-of-sale exports work as-is.

| Column | Required | Notes |
| --- | --- | --- |
| Date | ✅ | `date`, `sale_date`, `paid_at`, `invoice_date`, … |
| Amount | ✅ | `amount`, `total`, `price`, `paid`, … ($ signs and commas are cleaned automatically) |
| Service / item | optional | unlocks the "where your money comes from" breakdown |
| Staff | optional | adds a revenue-by-staff table when present |
| Payment method, client | optional | matched if present, not required |

A ready-made sample lives at `data/sales_receipts.csv`.

## Run it

```bash
# 1. create and activate a virtual environment
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux

# 2. install dependencies
python -m pip install -r requirements.txt

# 3a. launch the app
python -m streamlit run app.py

# 3b. or generate a report from the command line
python src/revenue_main.py                 # uses data/sales_receipts.csv
python src/revenue_main.py path/to/your_receipts.csv
```

> **Windows note:** if activating the venv is blocked, run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once in PowerShell.

## Optional AI summary

The plain-English recap uses the Anthropic API. To enable it, copy
`.env.example` to `.env` and add your key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

`.env` is git-ignored. Everything else in the app works without a key — the AI
recap is the only feature that needs one.

## Project layout

```
app.py                     Streamlit app (Revenue & Growth)
src/
  revenue_core.py          load, normalise, validate receipts + revenue KPIs
  revenue_history.py       local SQLite monthly history store
  revenue_trends.py        descriptive growth analysis (no recommendations)
  revenue_charts.py        chart specs + matplotlib (report) and Altair (app)
  revenue_report.py        markdown summary + optional AI recap
  revenue_main.py          command-line runner
  ai_summary.py            API-key handling + model selection
data/                      sample receipts
outputs/                   generated report + charts + history.db
legacy/                    archived earlier versions of the project
```

## Design principles

- **Deterministic core, AI optional.** Every number comes from your data. AI is
  additive and never required.
- **Honest by default.** If a column isn't there, the tool says so rather than
  inventing a figure. It never reports money you didn't actually take.
- **Descriptive, not prescriptive.** It tells you what's happening, not what to
  do — so you stay in charge of your own decisions.
