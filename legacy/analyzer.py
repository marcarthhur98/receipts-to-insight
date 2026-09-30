"""
analyzer.py — Analysis Engine (Stage 1 + 2, hardened)
=====================================================

Turns a CSV into facts: shape, types, missing values, numeric/categorical
split, descriptive stats, top categories, and data-quality checks.

This version is schema-agnostic and statistically careful:
  - ID-like columns are detected and EXCLUDED from numeric stats and outlier
    checks (a customer_id has no meaningful "mean" or "outlier").
  - Outlier detection skips low-cardinality discrete columns, where the IQR
    rule over-flags, and classifies a column as "skew" rather than "outliers"
    when a large share of values fall outside the IQR fence.

Every function returns plain data so the report and visual layers can reuse it.
"""

import warnings

import pandas as pd

# Tuning knobs for outlier detection.
MIN_UNIQUE_FOR_IQR = 15      # below this many distinct values, IQR isn't meaningful
SKEW_THRESHOLD_PCT = 10.0    # if >10% of a column is flagged, call it skew, not outliers


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_csv(path):
    """Read a CSV into a DataFrame with friendly errors."""
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        raise FileNotFoundError(f"Could not find a CSV file at: {path}")
    except Exception as error:
        raise ValueError(f"Could not read the CSV file. Reason: {error}")
    if df.empty:
        raise ValueError("The CSV file loaded but contains no rows.")
    return df


# ---------------------------------------------------------------------------
# Basic facts
# ---------------------------------------------------------------------------
def basic_info(df):
    return {
        "num_rows": df.shape[0],
        "num_columns": df.shape[1],
        "column_names": list(df.columns),
        "data_types": {col: str(dtype) for col, dtype in df.dtypes.items()},
    }


def missing_values(df):
    counts = df.isnull().sum()
    total_rows = len(df)
    result = {}
    for col, missing_count in counts.items():
        if missing_count > 0:
            result[col] = {
                "count": int(missing_count),
                "percent": round(missing_count / total_rows * 100, 2),
            }
    return result


def column_types(df):
    numeric_cols = list(df.select_dtypes(include="number").columns)
    categorical_cols = [c for c in df.columns if c not in numeric_cols]
    return {"numeric": numeric_cols, "categorical": categorical_cols}


# ---------------------------------------------------------------------------
# ID detection (used to exclude identifiers from numeric analysis)
# ---------------------------------------------------------------------------
def possible_id_columns(df):
    """
    Guess identifier columns: the name contains 'id', OR every value is unique
    and the column is not a float (real measurements can be unique by chance).
    """
    candidates = []
    total_rows = len(df)
    for col in df.columns:
        all_unique = df[col].nunique(dropna=True) == total_rows
        is_float = str(df[col].dtype).startswith("float")
        if "id" in col.lower() or (all_unique and not is_float):
            candidates.append(col)
    return candidates


def analysis_numeric_columns(df):
    """Numeric columns worth analysing = numeric columns minus ID-like ones."""
    ids = set(possible_id_columns(df))
    return [c for c in df.select_dtypes(include="number").columns if c not in ids]


# ---------------------------------------------------------------------------
# Descriptive statistics (IDs excluded)
# ---------------------------------------------------------------------------
def numeric_summary(df):
    summary = {}
    for col in analysis_numeric_columns(df):
        s = df[col]
        summary[col] = {
            "count": int(s.count()),
            "mean": round(float(s.mean()), 2),
            "min": round(float(s.min()), 2),
            "max": round(float(s.max()), 2),
            "std": round(float(s.std()), 2),
        }
    return summary


def top_categories(df, top_n=5):
    result = {}
    for col in column_types(df)["categorical"]:
        counts = df[col].value_counts().head(top_n)
        result[col] = {str(v): int(c) for v, c in counts.items()}
    return result


# ---------------------------------------------------------------------------
# Data-quality checks
# ---------------------------------------------------------------------------
def high_missing_columns(df, threshold=20.0):
    return {c: i["percent"] for c, i in missing_values(df).items() if i["percent"] > threshold}


def duplicate_rows(df):
    mask = df.duplicated()
    # Cap the index list so huge datasets don't dump thousands of numbers.
    return {"count": int(mask.sum()), "row_indices": df.index[mask].tolist()[:50]}


def possible_date_columns(df):
    candidates = []
    for col in df.select_dtypes(include="object").columns:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(df[col], errors="coerce")
        if parsed.notna().mean() >= 0.9:
            candidates.append(col)
    return candidates


def possible_categorical_columns(df, max_unique=20):
    date_cols = possible_date_columns(df)
    candidates = []
    for col in df.select_dtypes(include="object").columns:
        if col in date_cols:
            continue
        if df[col].nunique(dropna=True) <= max_unique:
            candidates.append(col)
    return candidates


def detect_outliers_iqr(df):
    """
    Skew-aware IQR outlier detection.

    For each numeric (non-ID) column with enough distinct values:
      - flag values beyond Q1 - 1.5*IQR or Q3 + 1.5*IQR,
      - record the share flagged,
      - if that share exceeds SKEW_THRESHOLD_PCT, label it "skew" (a long tail),
        otherwise "outliers" (a few extreme values).
    """
    result = {}
    ids = set(possible_id_columns(df))
    for col in df.select_dtypes(include="number").columns:
        if col in ids:
            continue
        s = df[col].dropna()
        if s.nunique() < MIN_UNIQUE_FOR_IQR:
            continue  # discrete / low-variance: IQR isn't meaningful
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        flagged = s[(s < lower) | (s > upper)]
        count = len(flagged)
        if count == 0:
            continue
        percent = round(count / len(s) * 100, 1)
        kind = "skew" if percent > SKEW_THRESHOLD_PCT else "outliers"
        result[col] = {
            "count": int(count),
            "percent": percent,
            "kind": kind,
            "lower_bound": round(float(lower), 2),
            "upper_bound": round(float(upper), 2),
            "example_values": [round(float(v), 2) for v in flagged.head(5)],
        }
    return result


# ---------------------------------------------------------------------------
# Aggregators
# ---------------------------------------------------------------------------
def data_quality(df, missing_threshold=20.0):
    return {
        "high_missing_columns": high_missing_columns(df, missing_threshold),
        "duplicate_rows": duplicate_rows(df),
        "possible_id_columns": possible_id_columns(df),
        "possible_date_columns": possible_date_columns(df),
        "possible_categorical_columns": possible_categorical_columns(df),
        "outliers": detect_outliers_iqr(df),
    }


def analyze(df):
    """Run all 