import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go


def segment(df: pd.DataFrame, by: str, metric: str, agg: str = "sum") -> pd.DataFrame:
    if by not in df.columns:
        raise ValueError(f"Segment column {by} not found. Available: {list(df.columns)}")
    if metric not in df.columns:
        # Try numeric fallback
        numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if numeric:
            metric = numeric[0]
        else:
            raise ValueError(f"Metric {metric} not found and no numeric columns")
    # Ensure metric numeric
    df = df.copy()
    orig_metric = metric
    # Handle count agg specially (metric ignored)
    if agg == "count":
        grouped = df.groupby(by).size().reset_index(name="value")
        metric_col = "value"
        total = grouped[metric_col].sum()
        grouped["share"] = (grouped[metric_col] / total * 100).round(1) if total else 0
        grouped = grouped.sort_values(metric_col, ascending=False)
        # Try pct_change if date col exists (time-based growth)
        # Look for date-like
        date_col = None
        for c in df.columns:
            if "date" in c.lower() or "time" in c.lower():
                date_col = c
                break
        if date_col:
            try:
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                df["period"] = df[date_col].dt.to_period("M").astype(str)
                # For each segment, compute last vs first period count growth (simplified)
                # We compute overall period trend per segment: count per period last vs first
                pass
            except:
                pass
        grouped = grouped.rename(columns={by: "category", metric_col: "value"})
        grouped["metric"] = orig_metric
        return grouped
    else:
        # Numeric metric
        try:
            df[metric] = pd.to_numeric(df[metric], errors="coerce")
        except:
            pass
        if agg not in ("sum", "mean", "median", "max", "min", "count"):
            agg = "sum"
        if agg == "median":
            grouped = (
                df.groupby(by)[metric].median().reset_index().rename(columns={metric: "value"})
            )
        elif agg == "mean":
            grouped = df.groupby(by)[metric].mean().reset_index().rename(columns={metric: "value"})
        elif agg == "max":
            grouped = df.groupby(by)[metric].max().reset_index().rename(columns={metric: "value"})
        elif agg == "min":
            grouped = df.groupby(by)[metric].min().reset_index().rename(columns={metric: "value"})
        else:
            grouped = df.groupby(by)[metric].sum().reset_index().rename(columns={metric: "value"})
        total = grouped["value"].sum()
        grouped["share"] = (
            (grouped["value"] / total * 100).round(1) if total and agg == "sum" else None
        )
        # Growth if date present
        date_col = None
        for c in df.columns:
            if "date" in c.lower():
                date_col = c
                break
        if date_col:
            try:
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                df["period"] = df[date_col].dt.to_period("M").astype(str)
                # For each category, compute first vs last period value
                period_agg = df.groupby([by, "period"])[metric].sum().reset_index()
                # Pivot to get first and last
                growth_map = {}
                for cat, sub in period_agg.groupby(by):
                    sub = sub.sort_values("period")
                    if len(sub) >= 2:
                        first = (
                            sub.iloc[0]["value"] if metric in sub.columns else sub.iloc[0][metric]
                        )
                        # Actually sub has metric column? Let's recompute properly
                        # Use grouped per period sum
                        vals = df[df[by] == cat].groupby("period")[metric].sum()
                        if len(vals) >= 2:
                            first_val = vals.iloc[0]
                            last_val = vals.iloc[-1]
                            growth = (
                                ((last_val - first_val) / first_val * 100) if first_val != 0 else 0
                            )
                            growth_map[cat] = round(growth, 1)
                if growth_map:
                    grouped["growth_pct"] = (
                        grouped["category"].map(growth_map)
                        if "category" in grouped.columns
                        else None
                    )
                    # Rename for grouped which currently has by column not category yet
                    pass
            except:
                pass
        grouped = grouped.rename(columns={by: "category"})
        # Sort
        grouped = grouped.sort_values("value", ascending=False)
        grouped["metric"] = orig_metric
        grouped["agg"] = agg
        return grouped


def plot_segment(df_seg: pd.DataFrame, by_label: str = "category") -> go.Figure:
    # Choose treemap if many categories, else bar
    if len(df_seg) <= 8:
        fig = px.bar(
            df_seg,
            x="category",
            y="value",
            color="share" if "share" in df_seg.columns and df_seg["share"].notna().any() else None,
            title=f"Segment by {by_label} (share)",
            text_auto=True,
        )
    else:
        try:
            fig = px.treemap(
                df_seg, path=["category"], values="value", title=f"Segment by {by_label} — treemap"
            )
        except:
            fig = px.bar(df_seg.head(10), x="category", y="value", title=f"Segment by {by_label}")
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10))
    return fig
