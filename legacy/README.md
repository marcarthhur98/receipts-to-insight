# Legacy — General-Purpose CSV Analyzer (archived)

This folder holds the original **general-purpose** version of the project: a tool
that profiled any CSV, ran data-quality checks, generated schema-agnostic charts,
and wrote an executive report with an optional AI summary.

It has been **superseded** by the booking-focused product in `src/` (the
Booking Operations Copilot). The code here is kept for reference and learning —
it is not part of the current product and is not maintained.

## What's here

- `analyzer.py` — generic profiling + data-quality checks (ID exclusion, skew-aware outliers)
- `visualizer.py` — schema-agnostic charts + AI-suggested chart renderer
- `report_generator.py` — executive markdown report
- `ai_summary.py` — Claude summary + chart suggestions
- `main.py` — CLI orchestrator
- `app.py` — Streamlit interface

## Running it (optional)

From the project root, with the virtual environment active:

```bash
python legacy/main.py data/sample.csv        # general CSV → report
streamlit run legacy/app.py                  # general CSV web app
```

These still work, but new development happens in the booking product.
