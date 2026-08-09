import io
import sys
import json
import traceback
import signal
import threading
from typing import Dict, Any, Optional, Tuple
import pandas as pd

from app.core.security import validate_code, get_safe_globals, SecurityError
from app.config import settings


class TimeoutException(Exception):
    pass


def _timeout_handler(signum, frame):
    raise TimeoutException("Execution timed out")


def execute_with_timeout(code: str, safe_globals: dict, local_vars: dict, timeout: int):
    """Execute code with timeout. Uses signal on Unix, thread fallback."""
    # Try signal method if available
    try:
        # Unix signal approach
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout)
            try:
                exec(code, safe_globals, local_vars)
                signal.alarm(0)
            except Exception:
                signal.alarm(0)
                raise
            return
    except Exception:
        pass

    # Fallback: thread with timeout
    result = {"exc": None}

    def target():
        try:
            exec(code, safe_globals, local_vars)
        except Exception as e:
            result["exc"] = e
            result["tb"] = traceback.format_exc()

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        # Can't kill thread, but we mark timeout
        raise TimeoutException(f"Execution timed out after {timeout}s")
    if result["exc"] is not None:
        # Re-raise with traceback
        raise result["exc"]


def dataframe_to_json(df: pd.DataFrame, max_rows: int = 100) -> Dict[str, Any]:
    """Convert DataFrame to JSON serializable dict for frontend."""
    if len(df) > max_rows:
        df_display = df.head(max_rows)
        truncated = True
    else:
        df_display = df
        truncated = False

    # Convert to records
    # Handle non-serializable types
    records = df_display.fillna("").to_dict(orient="records")
    # Ensure JSON serializable: convert numpy types, timestamps
    import numpy as np

    for rec in records:
        for k, v in rec.items():
            if isinstance(v, (np.integer,)):
                rec[k] = int(v)
            elif isinstance(v, (np.floating,)):
                rec[k] = float(v)
            elif isinstance(v, (pd.Timestamp,)):
                rec[k] = str(v)
            elif isinstance(v, (np.bool_,)):
                rec[k] = bool(v)
            else:
                try:
                    json.dumps(v)
                except:
                    rec[k] = str(v)

    return {
        "columns": [str(c) for c in df.columns.tolist()],
        "data": records,
        "rows": int(len(df)),
        "columns_count": int(len(df.columns)),
        "truncated": truncated,
        "display_rows": int(len(records)),
        # Also dtypes for UI
        "dtypes": {str(k): str(v) for k, v in df.dtypes.items()},
    }


def fig_to_json(fig) -> Optional[Dict[str, Any]]:
    """Convert Plotly fig to dict for frontend."""
    if fig is None:
        return None
    try:
        # Prefer to_json which is guaranteed JSON serializable
        if hasattr(fig, "to_json"):
            try:
                return json.loads(fig.to_json())
            except Exception:
                pass
        if hasattr(fig, "to_dict"):
            d = fig.to_dict()

            # Recursively convert ndarrays to lists
            def _convert(o):
                import numpy as np

                if isinstance(o, np.ndarray):
                    return o.tolist()
                if isinstance(o, dict):
                    return {k: _convert(v) for k, v in o.items()}
                if isinstance(o, (list, tuple)):
                    return [_convert(v) for v in o]
                if isinstance(o, (np.integer,)):
                    return int(o)
                if isinstance(o, (np.floating,)):
                    return float(o)
                if isinstance(o, (np.bool_,)):
                    return bool(o)
                return o

            return _convert(d)
        return None
    except Exception as e:
        print(f"Fig conversion failed: {e}")
        return None


def execute_code(code: str, df: pd.DataFrame, timeout: int = None) -> Dict[str, Any]:
    """
    Validate, execute code, return result.
    Expected code sets `result` and optionally `fig`.
    Returns: {success, result_json, chart_json, stdout, error, code}
    """
    if timeout is None:
        timeout = settings.execution_timeout_sec

    # Validate
    try:
        validate_code(code)
    except SecurityError as e:
        return {
            "success": False,
            "error": f"Security violation: {str(e)}",
            "stdout": "",
            "result_json": None,
            "chart_json": None,
            "code": code,
            "_after_df": None,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Validation failed: {str(e)}",
            "stdout": "",
            "result_json": None,
            "chart_json": None,
            "code": code,
            "_after_df": None,
        }

    # Prepare execution env
    safe_globals = get_safe_globals(df)
    local_vars = {}

    # Capture stdout
    old_stdout = sys.stdout
    stdout_capture = io.StringIO()
    sys.stdout = stdout_capture

    try:
        # Prepend to ensure result/fig are defined
        wrapped_code = code
        # Ensure code ends with no extra return
        execute_with_timeout(wrapped_code, safe_globals, local_vars, timeout)
        stdout_val = stdout_capture.getvalue()

        # Extract result and fig
        result = local_vars.get("result", None)
        fig = local_vars.get("fig", None)

        # If result is None, try to find last DataFrame variable or df itself
        if result is None:
            # Look for any DataFrame in local_vars
            for k, v in local_vars.items():
                if isinstance(v, pd.DataFrame):
                    result = v
                    break
            if result is None:
                # fallback: show head
                result = df.head(10)

        # Convert result to JSON
        result_json = None
        if isinstance(result, pd.DataFrame):
            result_json = dataframe_to_json(result)
        elif isinstance(result, pd.Series):
            # Convert Series to DataFrame
            result_json = dataframe_to_json(result.to_frame())
        elif isinstance(result, dict):
            # Try to convert dict to table
            try:
                tmp = pd.DataFrame([result])
                result_json = dataframe_to_json(tmp)
            except:
                result_json = {
                    "columns": ["value"],
                    "data": [{"value": str(result)}],
                    "rows": 1,
                    "columns_count": 1,
                    "truncated": False,
                    "display_rows": 1,
                }
        elif isinstance(result, list):
            try:
                tmp = pd.DataFrame(result)
                result_json = dataframe_to_json(tmp)
            except:
                result_json = {
                    "columns": ["value"],
                    "data": [{"value": str(v)} for v in result[:100]],
                    "rows": len(result),
                    "columns_count": 1,
                    "truncated": len(result) > 100,
                    "display_rows": min(len(result), 100),
                }
        else:
            # Single value
            result_json = {
                "columns": ["result"],
                "data": [{"result": str(result)}],
                "rows": 1,
                "columns_count": 1,
                "truncated": False,
                "display_rows": 1,
            }

        chart_json = fig_to_json(fig)
        # expose after_df for cleaning diff without second exec
        _after = None
        if isinstance(result, pd.DataFrame):
            _after = result
        elif isinstance(result, pd.Series):
            try:
                _after = result.to_frame()
            except:
                pass

        return {
            "success": True,
            "result_json": result_json,
            "chart_json": chart_json,
            "stdout": stdout_val,
            "error": None,
            "code": code,
            "_after_df": _after,
        }

    except TimeoutException as e:
        return {
            "success": False,
            "error": str(e),
            "stdout": stdout_capture.getvalue(),
            "result_json": None,
            "chart_json": None,
            "code": code,
            "_after_df": None,
        }
    except Exception as e:
        tb = traceback.format_exc()
        return {
            "success": False,
            "error": f"{str(e)}\n{tb}",
            "stdout": stdout_capture.getvalue(),
            "result_json": None,
            "chart_json": None,
            "code": code,
            "_after_df": None,
        }
    finally:
        sys.stdout = old_stdout
