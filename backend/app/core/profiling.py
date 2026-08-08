import pandas as pd
import numpy as np
from typing import Dict, Any

def profile_dataframe(df: pd.DataFrame, sample_n: int = 5) -> Dict[str, Any]:
    """Generate profiling info for LLM context and UI."""
    rows, cols = df.shape
    
    columns = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        nulls = int(df[col].isna().sum())
        non_nulls = int(rows - nulls)
        unique = int(df[col].nunique(dropna=True))
        sample_vals = df[col].dropna().head(3).tolist()
        # Convert to JSON serializable
        sample_vals = [str(v) for v in sample_vals]

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
            col_info["stats"] = {
                "mean": float(df[col].mean()) if non_nulls > 0 else None,
                "min": float(df[col].min()) if non_nulls > 0 else None,
                "max": float(df[col].max()) if non_nulls > 0 else None,
                "median": float(df[col].median()) if non_nulls > 0 else None,
                "std": float(df[col].std()) if non_nulls > 0 else None,
            }
        # Categorical stats
        elif df[col].dtype == object or pd.api.types.is_categorical_dtype(df[col]):
            top_vals = df[col].value_counts(dropna=True).head(5).to_dict()
            # Convert keys to string
            col_info["top_values"] = {str(k): int(v) for k, v in top_vals.items()}

        # Datetime detection
        # Try to infer if column looks like date
        if dtype == "object":
            try:
                # Sample check if parseable as date
                sample = df[col].dropna().head(5)
                if len(sample) > 0:
                    pd.to_datetime(sample, errors="raise")
                    col_info["inferred_type"] = "datetime"
            except Exception:
                pass

        columns.append(col_info)

    # Overall stats
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    
    # Try numeric describe
    try:
        describe = df.describe(include="all").fillna("").to_dict()
        # Make JSON serializable
        for k, v in describe.items():
            for kk, vv in v.items():
                if isinstance(vv, (np.integer, np.floating)):
                    v[kk] = float(vv)
                else:
                    v[kk] = str(vv)
    except Exception:
        describe = {}

    # Duplicates
    duplicates = int(df.duplicated().sum())

    # Sample rows
    sample_rows = df.head(sample_n).fillna("").to_dict(orient="records")
    # Convert values to string for safety
    for row in sample_rows:
        for k, v in row.items():
            if isinstance(v, (np.integer, np.floating)):
                row[k] = float(v)
            elif isinstance(v, (pd.Timestamp,)):
                row[k] = str(v)
            else:
                # Keep as is but ensure JSON serializable
                try:
                    import json
                    json.dumps(v)
                except:
                    row[k] = str(v)

    # Null summary
    null_summary = {str(col): int(df[col].isna().sum()) for col in df.columns}

    return {
        "shape": {"rows": int(rows), "columns": int(cols)},
        "columns": columns,
        "numeric_columns": [str(c) for c in numeric_cols],
        "categorical_columns": [str(c) for c in categorical_cols],
        "describe": describe,
        "duplicates": duplicates,
        "sample_rows": sample_rows,
        "null_summary": null_summary,
        "column_names": [str(c) for c in df.columns.tolist()],
    }

def get_profile_summary_text(profile: Dict[str, Any]) -> str:
    """Create compact text for LLM prompt."""
    lines = []
    lines.append(f"Dataset shape: {profile['shape']['rows']} rows x {profile['shape']['columns']} columns")
    lines.append(f"Columns: {', '.join(profile['column_names'])}")
    lines.append("Column details:")
    for col in profile["columns"]:
        line = f"- {col['name']} ({col['dtype']}), unique={col['unique']}, nulls={col['nulls']}, sample={col['sample_values']}"
        if "stats" in col:
            s = col["stats"]
            line += f", stats(mean={s['mean']:.2f} min={s['min']} max={s['max']})" if s["mean"] is not None else ""
        if "top_values" in col:
            line += f", top={col['top_values']}"
        lines.append(line)
    # Add sample rows
    lines.append("Sample rows (first 2):")
    for r in profile["sample_rows"][:2]:
        lines.append(str(r))
    return "\n".join(lines)
