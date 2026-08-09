import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple
import plotly.graph_objects as go


def _find_date_col(df: pd.DataFrame) -> Optional[str]:
    for c in df.columns:
        low = c.lower()
        if "date" in low or "time" in low or "day" in low:
            return c
    # Try parse
    for c in df.columns:
        try:
            sample = df[c].dropna().head(5)
            if len(sample) == 0:
                continue
            pd.to_datetime(sample, errors="raise")
            return c
        except Exception:
            continue
    return None


def _find_metric(df: pd.DataFrame, metric: Optional[str], profile: Dict[str, Any] = None) -> str:
    if metric and metric in df.columns and pd.api.types.is_numeric_dtype(df[metric]):
        return metric
    if metric and metric in df.columns:
        # try convert
        try:
            pd.to_numeric(df[metric].dropna().head(3), errors="raise")
            return metric
        except Exception:
            pass
    if profile and profile.get("numeric_columns"):
        return profile["numeric_columns"][0]
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            return c
    # fallback to last column
    return df.columns[-1] if len(df.columns) > 0 else "value"


def _resample_ts(df: pd.DataFrame, date_col: str, metric: str, freq: str = "M") -> pd.DataFrame:
    # Resample to frequency
    df_copy = df.copy()
    df_copy[date_col] = pd.to_datetime(df_copy[date_col], errors="coerce")
    df_copy = df_copy.dropna(subset=[date_col])
    if df_copy.empty:
        raise ValueError(f"No valid dates in {date_col}")
    df_copy = df_copy.sort_values(date_col)
    # If metric not numeric, sum count
    try:
        df_copy[metric] = pd.to_numeric(df_copy[metric], errors="coerce")
    except Exception:
        pass
    # Resample
    freq_map = {"D": "D", "W": "W", "M": "ME", "ME": "ME", "MS": "MS", "Q": "QE", "QE": "QE"}
    freq = freq_map.get(freq, "ME")
    # For monthly, use MonthEnd
    df_copy = df_copy.set_index(date_col)
    # Choose agg: sum for most metrics, but if metric looks like avg/price, use mean? Heuristic sum
    ts = df_copy[metric].resample(freq).sum()
    ts = ts.dropna()
    # Reset
    ts_df = ts.reset_index()
    ts_df.columns = ["ds", "y"]
    return ts_df


def _naive_forecast(
    ts_df: pd.DataFrame, periods: int, freq: str = "ME"
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    # Last value repeated
    last_val = ts_df["y"].iloc[-1] if not ts_df.empty else 0
    # Generate future dates
    last_date = ts_df["ds"].iloc[-1] if not ts_df.empty else pd.Timestamp.now()
    # freq to offset
    if freq in ("M", "ME"):
        offset = pd.offsets.MonthEnd(1)
    elif freq in ("W",):
        offset = pd.offsets.Week(1)
    elif freq in ("D",):
        offset = pd.offsets.Day(1)
    else:
        offset = pd.offsets.MonthEnd(1)
    future_dates = [last_date + offset * (i + 1) for i in range(periods)]
    forecast_df = pd.DataFrame(
        {
            "ds": future_dates,
            "yhat": [last_val] * periods,
            "yhat_lower": [last_val * 0.9] * periods,
            "yhat_upper": [last_val * 1.1] * periods,
        }
    )
    # Combine history + forecast for display
    hist = ts_df.rename(columns={"y": "yhat"})
    hist["yhat_lower"] = hist["yhat"]
    hist["yhat_upper"] = hist["yhat"]
    hist["is_forecast"] = False
    forecast_df["is_forecast"] = True
    combined = pd.concat([hist, forecast_df], ignore_index=True)
    combined["y"] = ts_df.set_index("ds")["y"].reindex(combined["ds"]).values  # history y
    return combined, {
        "method": "naive",
        "warning": "statsforecast not installed — naive last-value fallback",
        "periods": periods,
    }


def _statsforecast_forecast(
    ts_df: pd.DataFrame, periods: int, freq: str = "ME"
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    try:
        from statsforecast import StatsForecast
        from statsforecast.models import AutoETS, AutoARIMA
    except ImportError as e:
        raise ImportError("statsforecast not installed") from e
    # Prepare df for statsforecast: needs unique_id, ds, y
    sf_df = ts_df.copy()
    sf_df["unique_id"] = "series"
    # Choose models
    models = [
        AutoETS(season_length=12 if freq in ("M", "ME", "MS") else 1),
        AutoARIMA(season_length=12 if freq in ("M", "ME", "MS") else 1),
    ]
    # statsforecast expects ds as datetime
    sf = StatsForecast(models=models, freq=freq, n_jobs=1)
    # Forecast
    forecast_df = sf.forecast(df=sf_df, h=periods, level=[80, 95])
    # forecast_df has columns ds, AutoETS, AutoARIMA, etc. We'll average or pick ETS
    # It returns wide format
    # Convert to our format: ds, yhat, lower/upper
    # Use AutoETS as primary, fallback to first model
    model_col = None
    for cand in ["AutoETS", "AutoARIMA"]:
        if cand in forecast_df.columns:
            model_col = cand
            break
    if model_col is None:
        model_col = [c for c in forecast_df.columns if c not in ("unique_id", "ds")][0]
    # Confidence intervals: columns like AutoETS-lo-80 etc?
    lo80 = f"{model_col}-lo-80" if f"{model_col}-lo-80" in forecast_df.columns else None
    hi80 = f"{model_col}-hi-80" if f"{model_col}-hi-80" in forecast_df.columns else None
    # If not present, use 10% band
    yhat = forecast_df[model_col].values
    if lo80 and hi80:
        yhat_lower = forecast_df[lo80].values
        yhat_upper = forecast_df[hi80].values
    else:
        yhat_lower = yhat * 0.9
        yhat_upper = yhat * 1.1
    # Build combined
    hist = ts_df.copy()
    hist["is_forecast"] = False
    hist["yhat"] = hist["y"]
    hist["yhat_lower"] = hist["y"]
    hist["yhat_upper"] = hist["y"]
    future = pd.DataFrame(
        {
            "ds": forecast_df["ds"].values,
            "y": [None] * periods,
            "yhat": yhat,
            "yhat_lower": yhat_lower,
            "yhat_upper": yhat_upper,
            "is_forecast": True,
        }
    )
    combined = pd.concat([hist, future], ignore_index=True)
    # Backtest metrics: last 20% holdout if >=20 points
    metrics = {}
    n = len(ts_df)
    if n >= 20:
        holdout = max(1, int(n * 0.2))
        train = ts_df.iloc[:-holdout]
        test = ts_df.iloc[-holdout:]
        try:
            train_sf = train.copy()
            train_sf["unique_id"] = "series"
            sf2 = StatsForecast(models=[AutoETS(season_length=12)], freq=freq, n_jobs=1)
            pred = sf2.forecast(df=train_sf, h=holdout, level=[80])
            col = (
                "AutoETS"
                if "AutoETS" in pred.columns
                else [c for c in pred.columns if c not in ("unique_id", "ds")][0]
            )
            y_pred = pred[col].values
            y_true = test["y"].values
            mae = float(np.mean(np.abs(y_true - y_pred)))
            rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
            metrics = {
                "mae": round(mae, 2),
                "rmse": round(rmse, 2),
                "holdout": holdout,
                "method": model_col,
            }
        except Exception as e:
            metrics = {"method": model_col, "backtest_error": str(e)[:100]}
    else:
        metrics = {
            "method": model_col,
            "warning": f"Low data ({n} points) — forecast indicative, n<20 so no backtest",
            "n": n,
        }
    metrics["periods"] = periods
    return combined, metrics


def forecast(
    df: pd.DataFrame,
    date_col: Optional[str] = None,
    metric: Optional[str] = None,
    periods: int = 3,
    freq: str = "M",
    profile: Dict[str, Any] = None,
) -> Tuple[pd.DataFrame, go.Figure, Dict[str, Any]]:
    """
    Forecast metric over date_col for periods.
    Returns (combined_df, fig, metrics)
    """
    if df is None or df.empty:
        raise ValueError("Empty dataframe")
    if date_col is None:
        date_col = _find_date_col(df)
        if not date_col:
            raise ValueError(
                "No date column found — cannot forecast time-series. Available: "
                + ", ".join(df.columns)
            )
    if date_col not in df.columns:
        raise ValueError(f"Date column {date_col} not found")
    metric = _find_metric(df, metric, profile)
    # Resample
    ts_df = _resample_ts(df, date_col, metric, freq=freq)
    if len(ts_df) < 2:
        raise ValueError(
            f"Not enough time points after resampling ({len(ts_df)}). Need >=2 months of data."
        )
    warning = None
    if len(ts_df) < 12:
        warning = f"Low data ({len(ts_df)} points <12) — forecast indicative"
    # Try statsforecast, else naive
    try:
        combined, metrics = _statsforecast_forecast(
            ts_df, periods, freq="ME" if freq in ("M", "ME") else freq
        )
        method = metrics.get("method", "statsforecast")
    except ImportError:
        combined, metrics = _naive_forecast(ts_df, periods, freq=freq)
        method = "naive"
    except Exception as e:
        # Fallback to naive on error
        combined, metrics = _naive_forecast(ts_df, periods, freq=freq)
        metrics["fallback_reason"] = str(e)[:200]
        method = "naive"
    if warning:
        metrics["warning"] = warning
    metrics["date_col"] = date_col
    metrics["metric"] = metric
    metrics["history_points"] = len(ts_df)
    metrics["forecast_points"] = periods
    # Build figure: line history + forecast with band
    fig = go.Figure()
    # History line
    hist = combined[~combined["is_forecast"]]
    fc = combined[combined["is_forecast"]]
    fig.add_trace(
        go.Scatter(
            x=hist["ds"],
            y=hist["yhat"],
            mode="lines+markers",
            name="history",
            line=dict(color="#0f172a", width=2),
        )
    )
    # Forecast line
    fig.add_trace(
        go.Scatter(
            x=fc["ds"],
            y=fc["yhat"],
            mode="lines+markers",
            name="forecast",
            line=dict(color="#2563eb", width=2, dash="dash"),
        )
    )
    # Band
    fig.add_trace(
        go.Scatter(
            x=pd.concat([fc["ds"], fc["ds"][::-1]]),
            y=pd.concat([fc["yhat_upper"], fc["yhat_lower"][::-1]]),
            fill="toself",
            fillcolor="rgba(37,99,235,0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            name="80% band",
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        title=f"Forecast: {metric} next {periods} ({freq}) — {method} — {warning or ''}",
        xaxis_title=date_col,
        yaxis_title=metric,
        height=380,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    # Combined df for executor: need to return as result table with ds, y, yhat, band
    # Rename ds to date_col for display
    display_df = combined.rename(columns={"ds": date_col})
    return display_df, fig, metrics
