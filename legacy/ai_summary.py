"""
ai_summary.py — AI Insight Layer (concise, executive style)
===========================================================

Sends the analysis report to Claude and asks for a SHORT, decision-focused
summary — not a re-write of the whole report. The output is:

  - a 3-sentence executive summary
  - 3 executive insights
  - 3 operational risks
  - 3 recommended actions

SECURITY: the API key is read from the ANTHROPIC_API_KEY environment variable
(loaded from a local .env file via python-dotenv). It is never hardcoded, and
.env is git-ignored. See .env.example for the variable name.
"""

import json
import os
import re

from dotenv import load_dotenv

load_dotenv()  # load .env into environment variables (no-op if absent)


# A single place to choose the model. Sonnet balances quality, speed, and cost.
DEFAULT_MODEL = "claude-sonnet-4-6"

# The system prompt sets the model's role and tone for the whole request.
SYSTEM_PROMPT = (
    "You are a senior data analyst. Your job is to summarize the dataset "
    "analysis into concise business insights. Do not repeat the full technical "
    "report. Focus only on what matters for decision-making. Use short bullet "
    "points. Mention uncertainty where data quality issues exist."
)


def load_api_key():
    """Return the API key, or raise a clear, beginner-friendly error."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set.\n"
            "Fix: copy .env.example to a new file named .env and paste your key:\n"
            "    ANTHROPIC_API_KEY=your_real_key_here\n"
            "Create a key at https://console.anthropic.com/"
        )
    return api_key


def build_prompt(report_markdown):
    """
    Ask for a tight, structured summary. We specify the exact headings so the
    output is consistent and easy to drop into the report.
    """
    return (
        "Below is an automated analysis report for a dataset (in Markdown). "
        "Summarize it for busy decision-makers using EXACTLY these sections "
        "and headings, and nothing else:\n\n"
        "## Executive Summary\n"
        "(Exactly 3 sentences.)\n\n"
        "## 3 Executive Insights\n"
        "(Three short bullet points.)\n\n"
        "## 3 Operational Risks\n"
        "(Three short bullet points; note data-quality uncertainty where relevant.)\n\n"
        "## 3 Recommended Actions\n"
        "(Three short, practical bullet points.)\n\n"
        "Be concise, direct, and evidence-based. Use ONLY facts present in the "
        "report below — do not invent numbers.\n\n"
        "----- ANALYSIS REPORT -----\n"
        f"{report_markdown}"
    )


def generate_ai_summary(report_markdown, model=DEFAULT_MODEL, max_tokens=900):
    """
    Send the report to Claude and return the concise summary as a string.
    Raises a clear error if the key is missing or the API call fails.
    """
    api_key = load_api_key()

    # Imported here so the rest of the project runs even if 'anthropic' isn't
    # installed yet.
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    try:
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_prompt(report_markdown)}],
        )
    except Exception as error:
        raise RuntimeError(f"The AI request failed. Reason: {error}")

    parts = [block.text for block in message.content if hasattr(block, "text")]
    return "\n".join(parts).strip()


# ===========================================================================
# AI-SUGGESTED CHARTS
# ---------------------------------------------------------------------------
# Here the AI acts as the analyst that decides WHICH relationships are worth
# plotting. It returns a JSON array of chart specs; visualizer.render_chart_spec
# validates and renders each one. The model never emits plotting code.
# ===========================================================================
CHART_SYSTEM_PROMPT = (
    "You are a senior data analyst choosing the few most insightful charts for a "
    "dataset. You only propose charts that reveal meaningful relationships or "
    "distributions. You respond with JSON only — no prose."
)


def _dataframe_profile(df, max_cols=40):
    """Build a compact text profile of the columns for the model to reason over."""
    lines = []
    for col in list(df.columns)[:max_cols]:
        s = df[col]
        dtype = str(s.dtype)
        nunique = s.nunique(dropna=True)
        if str(dtype).startswith(("int", "float")):
            detail = f"min={s.min()}, median={s.median()}, max={s.max()}"
        else:
            tops = ", ".join(str(v) for v in s.value_counts().head(3).index)
            detail = f"top: {tops}"
        lines.append(f"- {col} ({dtype}, {nunique} unique) — {detail}")
    return "\n".join(lines)


def parse_chart_specs(text):
    """
    Tolerantly extract a JSON array of chart specs from the model's reply,
    whether it's raw JSON, fenced in ```json, or wrapped in prose. Returns [].
    """
    if not text:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            data = json.lo