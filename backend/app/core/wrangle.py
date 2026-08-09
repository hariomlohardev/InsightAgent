import pandas as pd
from typing import Dict, Any


def diff_dataframes(before: pd.DataFrame, after: pd.DataFrame) -> Dict[str, Any]:
    """Compute diff summary between before and after dataframes."""
    try:
        rows_before = int(before.shape[0])
        rows_after = int(after.shape[0])
        cols_before = int(before.shape[1])
        cols_after = int(after.shape[1])

        # Nulls
        try:
            nulls_before = int(before.isna().sum().sum())
            nulls_after = int(after.isna().sum().sum())
        except Exception:
            nulls_before = nulls_after = 0

        # Duplicates
        try:
            dups_before = int(before.duplicated().sum())
            dups_after = int(after.duplicated().sum())
        except Exception:
            dups_before = dups_after = 0

        # Dtypes changed
        try:
            dtypes_before = {str(c): str(before[c].dtype) for c in before.columns}
            dtypes_after = {str(c): str(after[c].dtype) for c in after.columns}
            dtypes_changed = {
                c: {"before": dtypes_before.get(c), "after": dtypes_after.get(c)}
                for c in set(list(dtypes_before.keys()) + list(dtypes_after.keys()))
                if dtypes_before.get(c) != dtypes_after.get(c)
            }
        except Exception:
            dtypes_changed = {}

        # Columns added/removed
        cols_added = [c for c in after.columns if c not in before.columns]
        cols_removed = [c for c in before.columns if c not in after.columns]

        return {
            "rows_before": rows_before,
            "rows_after": rows_after,
            "rows_added": max(0, rows_after - rows_before),
            "rows_removed": max(0, rows_before - rows_after),
            "cols_before": cols_before,
            "cols_after": cols_after,
            "cols_added": [str(c) for c in cols_added],
            "cols_removed": [str(c) for c in cols_removed],
            "nulls_before": nulls_before,
            "nulls_after": nulls_after,
            "nulls_fixed": max(0, nulls_before - nulls_after),
            "dups_before": dups_before,
            "dups_after": dups_after,
            "dups_removed": max(0, dups_before - dups_after),
            "dtypes_changed": dtypes_changed,
            "shape_changed": (rows_before != rows_after) or (cols_before != cols_after),
        }
    except Exception as e:
        return {
            "rows_before": 0,
            "rows_after": 0,
            "error": str(e),
            "shape_changed": False,
        }


def validate_clean_result(
    before: pd.DataFrame, after: pd.DataFrame, max_row_growth: float = 10.0
) -> Dict[str, Any]:
    """Validate that cleaning result is sane (no explosion, not empty unexpectedly)."""
    if after is None or not isinstance(after, pd.DataFrame):
        return {"valid": False, "reason": "Result is not a DataFrame"}
    if after.shape[0] == 0 and before.shape[0] > 0:
        # Empty after non-empty before might be ok for filter, but warn
        return {"valid": True, "warning": "Result is empty (all rows filtered)"}
    if after.shape[0] > before.shape[0] * max_row_growth:
        return {
            "valid": False,
            "reason": f"Row count exploded {before.shape[0]} -> {after.shape[0]}",
        }
    if after.shape[1] > before.shape[1] + 10:
        return {
            "valid": False,
            "reason": f"Too many columns added {before.shape[1]} -> {after.shape[1]}",
        }
    return {"valid": True}
