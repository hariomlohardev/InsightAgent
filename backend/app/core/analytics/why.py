import re
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
import numpy as np


# Helpers to find date column
def _find_date_col(df: pd.DataFrame) -> Optional[str]:
    candidates = []
    for c in df.columns:
        low = c.lower()
        if "date" in low or "time" in low or "day" in low or "month" in low or "year" in low:
            candidates.append(c)
    if candidates:
        return candidates[0]
    # try to parse any column as datetime
    for c in df.columns:
        try:
            sample = df[c].dropna().head(5)
            if len(sample) == 0:
                continue
            pd.to_datetime(sample, errors="raise")
            return c
        except:
            continue
    return None


def _find_metric_col(df: pd.DataFrame, query: str, profile: Dict[str, Any]) -> str:
    numeric = profile.get("numeric_columns", [])
    cols = profile.get("column_names", [])
    q = query.lower()
    for c in numeric:
        if c.lower() in q:
            return c
    # inferred_roles measure fallback
    for k, v in profile.get("inferred_roles", {}).items():
        if v == "measure" and k in numeric:
            return k
    if numeric:
        return numeric[0]
    if cols:
        return cols[0]
    return df.columns[0] if len(df.columns) > 0 else "value"


def _find_period(
    query: str, df: pd.DataFrame, date_col: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    # Extract month mentions like March, Jan, 2024-03
    month_map = {
        "january": 1,
        "jan": 1,
        "february": 2,
        "feb": 2,
        "march": 3,
        "mar": 3,
        "april": 4,
        "apr": 4,
        "may": 5,
        "june": 6,
        "jun": 6,
        "july": 7,
        "jul": 7,
        "august": 8,
        "aug": 8,
        "september": 9,
        "sep": 9,
        "sept": 9,
        "october": 10,
        "oct": 10,
        "november": 11,
        "nov": 11,
        "december": 12,
        "dec": 12,
    }
    q = query.lower()
    month = None
    for name, num in month_map.items():
        if re.search(rf"\b{name}\b", q):
            month = num
            break
    # year
    year_match = re.search(r"\b(20\d{2})\b", q)
    year = int(year_match.group(1)) if year_match else None
    # If we have date_col and month, we can split
    if date_col and month:
        # Determine period string like "2024-03"
        # If year not mentioned, infer from df's max date year
        try:
            dates = pd.to_datetime(df[date_col], errors="coerce")
            if year is None:
                # Use most common year in df
                year = int(dates.dt.year.mode().iloc[0]) if not dates.dropna().empty else 2024
            period_str = f"{year}-{month:02d}"
            # For comparison, pre is previous month
            # Return month as period key
            return period_str, date_col
        except:
            pass
    # Check for generic "last month" or "in march"
    if month:
        return f"month_{month}", date_col
    return None, date_col


def analyze_why(df: pd.DataFrame, profile: Dict[str, Any], query: str) -> pd.DataFrame:
    """
    Rule-based why analyzer.
    Splits df into pre/post (Mar vs Feb, or last vs prior cohort) and ranks contributors.
    Returns DataFrame with columns: category, delta, share, delta_pct, contribution_rank
    For line chart fallback, also includes period marker.
    """
    if df is None or df.empty:
        return pd.DataFrame([{"category": "no data", "delta": 0, "share": 0}])
    metric = _find_metric_col(df, query, profile)
    date_col = _find_date_col(df)
    period, _ = _find_period(query, df, date_col)

    # Find dimension to segment by: prefer categorical with moderate cardinality
    cat_cols = profile.get("categorical_columns", [])
    # Exclude datetime columns from segment candidates
    _inferred = profile.get("inferred_roles", {})
    _date_col_name = (date_col or "").lower()
    cat_cols = [
        c
        for c in cat_cols
        if _inferred.get(c) != "datetime"
        and c.lower() != _date_col_name
        and "date" not in c.lower()
        and "time" not in c.lower()
    ]
    # If no cat_cols after filtering, fallback to any non-numeric non-datetime
    if not cat_cols:
        cat_cols = [
            c
            for c in df.columns
            if c != metric and df[c].dtype == object and c != date_col and "date" not in c.lower()
        ]
    if not cat_cols:
        # fallback to first column not metric
        for c in df.columns:
            if c != metric:
                cat_cols = [c]
                break
    segment_col = cat_cols[0] if cat_cols else df.columns[0]

    # Try time split if date_col exists and period detected
    df_copy = df.copy()
    # Ensure metric numeric
    try:
        df_copy[metric] = pd.to_numeric(df_copy[metric], errors="coerce").fillna(0)
    except:
        pass

    # If date_col present, parse
    if date_col and date_col in df_copy.columns:
        try:
            df_copy["_parsed_date"] = pd.to_datetime(df_copy[date_col], errors="coerce")
            df_copy["_month"] = df_copy["_parsed_date"].dt.month
            df_copy["_year"] = df_copy["_parsed_date"].dt.year
        except:
            date_col = None

    pre = None
    post = None
    period_label = "overall"
    if period and date_col and "_month" in df_copy.columns:
        # period like "2024-03" or "month_3"
        try:
            month_num = None
            if period.startswith("month_"):
                month_num = int(period.split("_")[1])
                period_label = period
            elif "-" in period:
                month_num = int(period.split("-")[1])
                period_label = period
            if month_num:
                # post = that month, pre = previous month (or all before if not enough)
                post_mask = df_copy["_month"] == month_num
                pre_mask = df_copy["_month"] == (month_num - 1 if month_num > 1 else 12)
                # If pre is empty, use all months before post
                if pre_mask.sum() == 0:
                    pre_mask = df_copy["_month"] < month_num
                if post_mask.sum() > 0:
                    post = df_copy[post_mask]
                    pre = df_copy[pre_mask] if pre_mask.sum() > 0 else df_copy[~post_mask]
                    period_label = f"month {month_num} vs prior"
        except:
            pass

    # Fallback: if no time split, split by median of metric? No — use cohort diff by segment_col overall deltas vs overall?
    # Better: compare top category vs rest or recent vs older if no date: use last 30% rows as post (proxy for recent)
    if pre is None or post is None or pre.empty or post.empty:
        # Use row order split: last 30% as post
        n = len(df_copy)
        split_idx = int(n * 0.7)
        if n >= 6:
            pre = df_copy.iloc[:split_idx]
            post = df_copy.iloc[split_idx:]
            period_label = "recent vs prior (row split)"
        else:
            # Small df: use overall breakdown by segment_col (no pre/post) — just show share
            grouped = df_copy.groupby(segment_col)[metric].sum().reset_index()
            total = grouped[metric].sum()
            grouped["share"] = (grouped[metric] / total * 100).round(1) if total != 0 else 0
            grouped["delta"] = grouped[metric]  # no delta
            grouped["delta_pct"] = 0
            grouped = grouped.sort_values(metric, ascending=False).head(5)
            grouped = grouped.rename(columns={segment_col: "category"})
            grouped["period"] = period_label
            grouped["contribution"] = grouped["share"]
            return grouped[["category", metric, "share", "delta"]].rename(columns={metric: "delta"})

    # Now we have pre/post
    # Aggregate by segment_col
    pre_agg = pre.groupby(segment_col)[metric].sum().reset_index().rename(columns={metric: "pre"})
    post_agg = (
        post.groupby(segment_col)[metric].sum().reset_index().rename(columns={metric: "post"})
    )
    merged = pd.merge(pre_agg, post_agg, on=segment_col, how="outer").fillna(0)
    merged["delta"] = merged["post"] - merged["pre"]
    # delta_pct: avoid div by zero
    merged["delta_pct"] = np.where(
        merged["pre"] != 0,
        (merged["delta"] / merged["pre"] * 100).round(1),
        np.where(merged["post"] != 0, 100.0, 0.0),
    )
    total_delta = merged["delta"].sum()
    # contribution: delta / total_delta weighted; if total_delta 0, use absolute delta share
    if total_delta != 0:
        merged["contribution"] = (merged["delta"] / total_delta * 100).round(1)
    else:
        # use post share
        total_post = merged["post"].sum()
        merged["contribution"] = (
            (merged["post"] / total_post * 100).round(1) if total_post != 0 else 0
        )
    # Absolute impact for ranking: sort by most negative delta if query mentions drop/decrease, else most positive if increase, else largest absolute
    q_low = query.lower()
    is_drop = any(w in q_low for w in ["drop", "decrease", "down", "fall", "decline", "low"])
    is_increase = any(w in q_low for w in ["increase", "up", "rise", "high", "growth"])
    if is_drop:
        merged = merged.sort_values("delta", ascending=True)  # most negative first
    elif is_increase:
        merged = merged.sort_values("delta", ascending=False)
    else:
        merged = merged.reindex(merged["delta"].abs().sort_values(ascending=False).index)
    merged = merged.head(5)
    merged = merged.rename(columns={segment_col: "category"})
    merged["period"] = period_label
    # Keep cols for display
    cols = ["category", "pre", "post", "delta", "delta_pct", "contribution", "period"]
    for c in cols:
        if c not in merged.columns:
            merged[c] = 0
    return merged[cols]


def what_if(
    df: pd.DataFrame, col: str, pct: float, metric: str = None, by: str = None, agg: str = "sum"
) -> pd.DataFrame:
    """
    What-if: clone df, multiply col by (1+pct/100), re-aggregate metric by `by` or overall.
    Returns DataFrame with comparison: category, before, after, delta, delta_pct
    """
    if col not in df.columns:
        raise ValueError(f"Column {col} not found. Available: {list(df.columns)}")
    # Ensure numeric
    try:
        df_before = df.copy()
        df_after = df.copy()
        df_after[col] = pd.to_numeric(df_after[col], errors="coerce") * (1 + pct / 100)
    except Exception as e:
        raise ValueError(f"What-if failed: {e}")

    if metric is None:
        # Use col as metric if numeric, else first numeric
        if pd.api.types.is_numeric_dtype(df[col]):
            metric = col
        else:
            numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            metric = numeric[0] if numeric else col

    if by is None or by not in df.columns:
        # Overall single row
        try:
            before_val = pd.to_numeric(df_before[metric], errors="coerce").sum()
            after_val = pd.to_numeric(df_after[metric], errors="coerce").sum()
        except:
            before_val = 0
            after_val = 0
        delta = after_val - before_val
        delta_pct = (delta / before_val * 100) if before_val != 0 else 0
        return pd.DataFrame(
            [
                {
                    "category": "overall",
                    "before": round(before_val, 2),
                    "after": round(after_val, 2),
                    "delta": round(delta, 2),
                    "delta_pct": round(delta_pct, 1),
                    "scenario": f"{col} {pct:+}%",
                }
            ]
        )
    else:
        # Groupby
        agg_func = agg if agg in ("sum", "mean", "median", "count", "max", "min") else "sum"
        if agg_func == "count":
            before_agg = df_before.groupby(by).size().reset_index(name="before")
            after_agg = df_after.groupby(by).size().reset_index(name="after")
        else:
            # For mean/median etc, use corresponding
            before_agg = (
                df_before.groupby(by)[metric]
                .agg(agg_func)
                .reset_index()
                .rename(columns={metric: "before"})
            )
            after_agg = (
                df_after.groupby(by)[metric]
                .agg(agg_func)
                .reset_index()
                .rename(columns={metric: "after"})
            )
        merged = pd.merge(before_agg, after_agg, on=by, how="outer").fillna(0)
        merged["delta"] = merged["after"] - merged["before"]
        merged["delta_pct"] = np.where(
            merged["before"] != 0, merged["delta"] / merged["before"] * 100, 0
        ).round(1)
        merged = merged.rename(columns={by: "category"})
        merged["scenario"] = f"{col} {pct:+}%"
        return merged[["category", "before", "after", "delta", "delta_pct", "scenario"]]
