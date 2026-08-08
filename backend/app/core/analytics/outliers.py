import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

def find_outliers(df: pd.DataFrame, col: str, method: str = "iqr", z_thresh: float = 3.0):
    if col not in df.columns:
        raise ValueError(f"Column {col} not found. Available: {list(df.columns)}")
    s = pd.to_numeric(df[col], errors="coerce")
    if s.isna().all():
        raise ValueError(f"Column {col} has no numeric data")
    n = len(s)
    # Dropna for stats
    clean = s.dropna()
    if method == "zscore" or method == "z":
        mean = clean.mean()
        std = clean.std(ddof=0)
        if std == 0 or np.isnan(std):
            # No variation -> no outliers
            df_flagged = df.copy()
            df_flagged["is_outlier"] = False
            return {
                "method": "zscore",
                "mean": float(mean),
                "std": float(std),
                "threshold": z_thresh,
                "outliers": 0,
                "df_flagged": df_flagged,
            }
        z = (clean - mean) / std
        outlier_mask = z.abs() > z_thresh
        lower = mean - z_thresh * std
        upper = mean + z_thresh * std
        Q1 = Q3 = IQR = None
    else:  # iqr
        Q1 = clean.quantile(0.25)
        Q3 = clean.quantile(0.75)
        IQR = Q3 - Q1
        if IQR == 0 or np.isnan(IQR):
            # Fallback to zscore if IQR zero
            mean = clean.mean()
            std = clean.std(ddof=0)
            if std == 0:
                df_flagged = df.copy()
                df_flagged["is_outlier"] = False
                return {"method": "iqr", "Q1": float(Q1), "Q3": float(Q3), "IQR": float(IQR), "lower": float(Q1), "upper": float(Q3), "outliers": 0, "df_flagged": df_flagged}
            mean = clean.mean()
            lower = mean - z_thresh * std
            upper = mean + z_thresh * std
            outlier_mask = (s < lower) | (s > upper)
        else:
            lower = Q1 - 1.5 * IQR
            upper = Q3 + 1.5 * IQR
            outlier_mask = (s < lower) | (s > upper)
        mean = clean.mean()
        std = clean.std(ddof=0)

    df_flagged = df.copy()
    # Align mask to original index (s has same index as df)
    flag_series = pd.Series(False, index=df.index)
    # outlier_mask is indexed like clean (subset). Map back
    # For iqr, outlier_mask is for full s (with NaNs false); for zscore, need to map
    if method in ("zscore","z"):
        # z was computed on clean only
        full_z = (s - mean) / std if std != 0 else pd.Series(0, index=s.index)
        flag_series = full_z.abs() > z_thresh
    else:
        flag_series = (s < lower) | (s > upper)
    flag_series = flag_series.fillna(False)
    df_flagged["is_outlier"] = flag_series.values
    outlier_count = int(flag_series.sum())
    # Stats dict
    stats = {
        "method": method,
        "column": col,
        "rows": int(n),
        "outliers": outlier_count,
        "outlier_pct": round(outlier_count / n * 100, 2) if n else 0,
        "mean": float(mean) if not np.isnan(mean) else None,
        "std": float(std) if not np.isnan(std) else None,
    }
    if method == "iqr" or "Q1" in locals():
        stats.update({"Q1": float(Q1) if Q1 is not None else None, "Q3": float(Q3) if Q3 is not None else None, "IQR": float(IQR) if IQR is not None else None, "lower": float(lower), "upper": float(upper)})
    else:
        stats.update({"lower": float(lower), "upper": float(upper), "threshold": z_thresh})
    stats["df_flagged"] = df_flagged
    return stats

def plot_outliers(df_flagged: pd.DataFrame, col: str, date_col: str = None):
    # Scatter with outliers red
    if date_col and date_col in df_flagged.columns:
        try:
            x = pd.to_datetime(df_flagged[date_col], errors="coerce")
            if x.isna().all():
                x = df_flagged.index
            else:
                x = df_flagged[date_col]
        except:
            x = df_flagged.index
        xlabel = date_col
    else:
        x = df_flagged.index
        xlabel = "index"
    # Build figure
    # Use go.Scatter for control
    normal = df_flagged[~df_flagged["is_outlier"]]
    outliers = df_flagged[df_flagged["is_outlier"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=normal[xlabel] if xlabel != "index" else normal.index, y=normal[col], mode="markers", name="normal", marker=dict(color="#64748b", size=6, opacity=0.7)))
    if not outliers.empty:
        fig.add_trace(go.Scatter(x=outliers[xlabel] if xlabel != "index" else outliers.index, y=outliers[col], mode="markers", name="outlier", marker=dict(color="#dc2626", size=10, symbol="x")))
    fig.update_layout(title=f"Outliers in {col} ({len(outliers)} flagged)", xaxis_title=xlabel, yaxis_title=col, height=380, margin=dict(l=10,r=10,t=40,b=10))
    return fig
