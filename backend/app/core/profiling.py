import os
import time
import pandas as pd
import numpy as np
import re
from typing import Dict, Any


def profile_dataframe(
    df: pd.DataFrame,
    sample_n: int = 5,
    use_cache: bool = True,
    dataset_id: str = None,
    version: int = None,
) -> Dict[str, Any]:
    """Generate profiling info for LLM context and UI. Robust for empty, wide, dirty files. Cached 60s if use_cache."""
    _dbg = os.getenv("DEBUG_PROFILE", "0") in ("1", "true", "yes")
    _t0 = time.time() if _dbg else 0
    _timings = {} if _dbg else None
    # Cache check — key by dataset_id:version when provided (correct invalidation), else fallback to shape hash
    if use_cache:
        try:
            from app.core.cache import get as cache_get, set as cache_set, cache_key

            if dataset_id is not None:
                # Primary key for 10.2: profile:{dataset_id}:{version}
                ck = cache_key(f"profile:{dataset_id}:{version if version is not None else 0}")
            else:
                # Stable fallback key (no id(df) — use content hash for versioned datasets, shape+cols for ad-hoc)
                try:
                    # Use hash of first row values as stable identity for ad-hoc DFs
                    _sample_hash = (
                        str(hash(tuple(map(str, df.head(1).values.flatten().tolist()))))
                        if len(df) > 0
                        else "empty"
                    )
                except Exception:
                    _sample_hash = "0"
                ck = cache_key(
                    "profile",
                    str(df.shape),
                    ",".join(map(str, df.columns[:5])),
                    _sample_hash[:12],
                )
            cached = cache_get(ck)
            if cached and isinstance(cached, dict):
                # Validate that cached is a profile (not a dataset response polluted by old bug)
                # Old bug cached full ProfileResponse under profile:{id}:{ver} — detect and ignore
                if "dataset" in cached and "profile" in cached:
                    # This is a dataset response, not a profile — treat as miss and recompute
                    pass
                elif "numeric_columns" in cached and "categorical_columns" in cached:
                    return cached
                elif "column_names" in cached and "inferred_roles" in cached:
                    return cached
        except:
            pass
    # Guard empty df
    if df is None or df.shape[1] == 0:
        return {
            "shape": {"rows": 0, "columns": 0},
            "columns": [],
            "numeric_columns": [],
            "categorical_columns": [],
            "describe": {},
            "duplicates": 0,
            "sample_rows": [],
            "null_summary": {},
            "column_names": [],
            "inferred_roles": {},
        }

    rows, cols = df.shape

    # Handle empty rows but with columns
    if rows == 0:
        columns = []
        for col in df.columns:
            columns.append(
                {
                    "name": str(col),
                    "dtype": str(df[col].dtype),
                    "nulls": 0,
                    "non_nulls": 0,
                    "unique": 0,
                    "sample_values": [],
                    "inferred_type": "empty",
                }
            )
        return {
            "shape": {"rows": 0, "columns": int(cols)},
            "columns": columns,
            "numeric_columns": [
                str(c) for c in df.select_dtypes(include=[np.number]).columns.tolist()
            ],
            "categorical_columns": [
                str(c)
                for c in df.select_dtypes(include=["object", "category", "string"]).columns.tolist()
            ],
            "describe": {},
            "duplicates": 0,
            "sample_rows": [],
            "null_summary": {str(col): 0 for col in df.columns},
            "column_names": [str(c) for c in df.columns.tolist()],
            "inferred_roles": {str(c): "dimension" for c in df.columns.tolist()},
        }

    columns = []
    inferred_roles = {}

    # Regex for date-like strings (YYYY-MM-DD, MM/DD/YYYY, etc)
    date_pattern = re.compile(
        r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$|^\d{1,2}[-/]\d{1,2}[-/]\d{4}$|^\d{4}[-/]\d{1,2}[-/]\d{1,2} \d{1,2}:\d{2}"
    )

    # BF-02 vectorized hot path: compute nulls/nunique once (was per-col loop 38% of 1.8s)
    try:
        _null_counts = df.isna().sum()
        _nunique_counts = df.nunique(dropna=True)
    except Exception:
        _null_counts = None
        _nunique_counts = None

    for col in df.columns:
        dtype = str(df[col].dtype)
        # vectorized lookup, fallback to per-col if vectorized failed
        try:
            if _null_counts is not None:
                nulls = int(_null_counts[col])
            else:
                nulls = int(df[col].isna().sum())
        except Exception:
            nulls = int(df[col].isna().sum()) if col in df.columns else 0
        non_nulls = int(rows - nulls)
        try:
            if _nunique_counts is not None:
                unique = int(_nunique_counts[col])
            else:
                unique = int(df[col].nunique(dropna=True))
        except Exception:
            try:
                unique = int(df[col].nunique(dropna=True))
            except Exception:
                unique = 0
        try:
            sample_vals = df[col].dropna().head(3).tolist()
            sample_vals = [str(v) for v in sample_vals]
        except Exception:
            sample_vals = []

        col_info = {
            "name": str(col),
            "dtype": dtype,
            "nulls": nulls,
            "non_nulls": non_nulls,
            "unique": unique,
            "sample_values": sample_vals,
        }

        # Numeric stats
        if pd.api.types.is_numeric_dtype(df[col]):
            try:
                col_info["stats"] = {
                    "mean": float(df[col].mean()) if non_nulls > 0 else None,
                    "min": float(df[col].min()) if non_nulls > 0 else None,
                    "max": float(df[col].max()) if non_nulls > 0 else None,
                    "median": float(df[col].median()) if non_nulls > 0 else None,
                    "std": float(df[col].std()) if non_nulls > 0 else None,
                }
                inferred_roles[str(col)] = "measure"
            except Exception:
                inferred_roles[str(col)] = "measure"
        # Categorical stats — BF-02 skip value_counts when unique >1000 (saves 270ms on high-cardinality date)
        elif (
            df[col].dtype == object
            or pd.api.types.is_string_dtype(df[col])
            or pd.api.types.is_categorical_dtype(df[col])
        ):
            if 1 < unique < 1000:
                try:
                    top_vals = df[col].value_counts(dropna=True).head(5).to_dict()
                    col_info["top_values"] = {str(k): int(v) for k, v in top_vals.items()}
                except Exception:
                    col_info["top_values"] = {}
            else:
                col_info["top_values"] = {}

            # Datetime detection - only on string-like cols with date-like sample (object/string/str in pandas 2/3)
            # In pandas 3 dtype may be 'str' or 'string'; use is_string_dtype for robustness
            is_str_like = False
            try:
                is_str_like = pd.api.types.is_string_dtype(df[col]) or dtype == "object"
            except Exception:
                is_str_like = dtype == "object" or "str" in dtype.lower()
            if is_str_like:
                try:
                    sample = df[col].dropna().head(5)
                    if len(sample) > 0:
                        # Only try if sample looks date-like via regex
                        sample_str = [str(v) for v in sample]
                        if any(date_pattern.match(s.strip()) for s in sample_str):
                            # Use coerce, not raise, to avoid warnings
                            parsed = pd.to_datetime(sample, errors="coerce", utc=False)
                            if not parsed.isna().all():
                                col_info["inferred_type"] = "datetime"
                                inferred_roles[str(col)] = "datetime"
                except Exception:
                    pass
            # Default role for string-like is dimension (if not already set as datetime)
            if str(col) not in inferred_roles:
                inferred_roles[str(col)] = "dimension"
        else:
            # datetime etc (pandas 3 string dtype -> dimension)
            inferred_roles[str(col)] = (
                "dimension"
                if "object" in dtype or "category" in dtype or "string" in dtype.lower()
                else "measure"
            )

        columns.append(col_info)

    # Overall stats
    try:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    except Exception:
        numeric_cols = []
    try:
        # include string dtype for pandas 3.0
        categorical_cols = df.select_dtypes(
            include=["object", "category", "string"]
        ).columns.tolist()
    except Exception:
        # fallback without string if pandas <2
        try:
            categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
        except Exception:
            categorical_cols = []

    # Try numeric describe, limit to 20 cols to avoid blowup on wide files
    try:
        # Limit df for describe if wide
        if len(df.columns) > 20:
            describe_df = df.iloc[:, :20]
        else:
            describe_df = df
        describe = describe_df.describe(include="all").fillna("").to_dict()
        for k, v in describe.items():
            for kk, vv in v.items():
                if isinstance(vv, (np.integer, np.floating)):
                    v[kk] = float(vv)
                else:
                    v[kk] = str(vv)
    except Exception:
        describe = {}

    # Duplicates — BF-02 skip for >1M or >20 cols (15% of 1.8s, not needed for chat)
    try:
        if rows > 1_000_000 or cols > 20:
            duplicates = 0
        else:
            duplicates = int(df.duplicated().sum())
    except Exception:
        duplicates = 0

    # Sample rows
    try:
        sample_rows = df.head(sample_n).fillna("").to_dict(orient="records")
        for row in sample_rows:
            for k, v in list(row.items()):
                if isinstance(v, (np.integer, np.floating)):
                    row[k] = float(v)
                elif isinstance(v, (pd.Timestamp,)):
                    row[k] = str(v)
                else:
                    try:
                        import json

                        json.dumps(v)
                    except:
                        row[k] = str(v)
    except Exception:
        sample_rows = []

    # Null summary — reuse vectorized _null_counts when available
    try:
        if _null_counts is not None:
            null_summary = {str(col): int(_null_counts[col]) for col in df.columns}
        else:
            null_summary = {str(col): int(df[col].isna().sum()) for col in df.columns}
    except Exception:
        try:
            null_summary = {str(col): int(df[col].isna().sum()) for col in df.columns}
        except Exception:
            null_summary = {}

    result = {
        "shape": {"rows": int(rows), "columns": int(cols)},
        "columns": columns,
        "numeric_columns": [str(c) for c in numeric_cols],
        "categorical_columns": [str(c) for c in categorical_cols],
        "describe": describe,
        "duplicates": duplicates,
        "sample_rows": sample_rows,
        "null_summary": null_summary,
        "column_names": [str(c) for c in df.columns.tolist()],
        "inferred_roles": inferred_roles,
    }
    if _dbg:
        try:
            total_ms = (time.time() - _t0) * 1000
            import sys

            print(
                f"DEBUG_PROFILE profile_dataframe rows={rows} cols={cols} total_ms={total_ms:.1f}",
                file=sys.stderr,
            )
        except:
            pass
    if use_cache:
        try:
            from app.core.cache import set as cache_set, cache_key

            if dataset_id is not None:
                ck = cache_key(f"profile:{dataset_id}:{version if version is not None else 0}")
            else:
                ck = cache_key(
                    "profile", str(result["shape"]), ",".join(map(str, result["column_names"][:5]))
                )
            cache_set(ck, result, ttl=60)
        except:
            pass
    return result


def get_profile_summary_text(profile: Dict[str, Any]) -> str:
    """Create compact text for LLM prompt."""
    lines = []
    lines.append(
        f"Dataset shape: {profile['shape']['rows']} rows x {profile['shape']['columns']} columns"
    )
    lines.append(f"Columns: {', '.join(profile['column_names'])}")
    if profile.get("inferred_roles"):
        lines.append(f"Roles: {profile['inferred_roles']}")
    lines.append("Column details:")
    for col in profile["columns"]:
        line = f"- {col['name']} ({col['dtype']}), unique={col['unique']}, nulls={col['nulls']}, sample={col['sample_values']}"
        if "stats" in col:
            s = col["stats"]
            if s["mean"] is not None:
                try:
                    line += f", stats(mean={s['mean']:.2f} min={s['min']} max={s['max']})"
                except:
                    pass
        if "top_values" in col:
            line += f", top={col['top_values']}"
        if "inferred_type" in col:
            line += f", inferred={col['inferred_type']}"
        lines.append(line)
    lines.append("Sample rows (first 2):")
    for r in profile["sample_rows"][:2]:
        lines.append(str(r))
    return "\n".join(lines)
