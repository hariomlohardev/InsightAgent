from typing import Dict, Any
import pandas as pd

from app.core import storage
from app.core.profiling import profile_dataframe
from app.core.wrangle import diff_dataframes, validate_clean_result
from app.agent import coder, executor
from app.agent.executor import dataframe_to_json, fig_to_json


async def preview_clean(dataset_id: str, query: str) -> Dict[str, Any]:
    """Preview cleaning without mutating. Returns diff, preview, code, etc."""
    import asyncio

    df = await asyncio.to_thread(storage.load_dataset_df, dataset_id)
    try:
        _meta = storage.get_dataset_meta(dataset_id)
        _ver = _meta.get("current_version", 0) if _meta else 0
    except:
        _ver = 0
    profile = await asyncio.to_thread(profile_dataframe, df, 5, True, dataset_id, _ver)

    # Generate code via coder (cleaning branch)
    # Force intent to cleaning for preview
    intent = {"intent": "cleaning", "chart_type": "none", "columns": [], "aggregation": ""}
    code_res = await coder.generate_code(query, profile, intent)
    # If coder didn't return cleaning code (e.g., fallback to top N), try fallback_coder directly with cleaning
    # But coder already handles cleaning detection via keywords, so it should be cleaning
    code = code_res["code"]
    explanation = code_res.get("explanation", "")

    # Validate code
    from app.core.security import validate_code, SecurityError

    try:
        validate_code(code)
    except SecurityError as e:
        return {
            "success": False,
            "error": f"Security violation: {str(e)}",
            "code": code,
            "explanation": explanation,
            "diff": None,
            "preview": None,
            "chart": None,
        }

    # Execute once — capture after_df from executor
    import asyncio as _asyncio

    exec_res = await _asyncio.to_thread(executor.execute_code, code, df)

    if not exec_res["success"]:
        return {
            "success": False,
            "error": exec_res["error"],
            "code": code,
            "explanation": explanation,
            "diff": None,
            "preview": exec_res.get("result_json"),
            "chart": exec_res.get("chart_json"),
            "stdout": exec_res.get("stdout"),
        }

    after_df = exec_res.get("_after_df")
    if not isinstance(after_df, pd.DataFrame):
        # Fallback for shape code
        if "drop_duplicates" in code:
            try:
                after_df = df.drop_duplicates()
            except Exception:
                after_df = df
        else:
            after_df = df

    # Compute diff
    try:
        diff = diff_dataframes(df, after_df)
        validation = validate_clean_result(df, after_df)
        diff["validation"] = validation
    except Exception as e:
        diff = {"error": str(e)}

    # Prepare preview (after head)
    try:
        preview = (
            dataframe_to_json(after_df.head(10), max_rows=10)
            if isinstance(after_df, pd.DataFrame)
            else exec_res.get("result_json")
        )
        chart = exec_res.get("chart_json")
        # Also before preview for comparison?
        before_preview = dataframe_to_json(df.head(10), max_rows=10)
    except Exception:
        preview = exec_res.get("result_json")
        chart = exec_res.get("chart_json")
        before_preview = None

    return {
        "success": True,
        "code": code,
        "explanation": explanation,
        "diff": diff,
        "preview": preview,
        "before_preview": before_preview,
        "chart": chart,
        "result": exec_res.get("result_json"),
        "error": None,
        "stdout": exec_res.get("stdout"),
    }


async def apply_clean(dataset_id: str, query: str, code: str = None) -> Dict[str, Any]:
    """Apply cleaning: execute code, create new version, return new meta and diff."""
    import asyncio

    df = await asyncio.to_thread(storage.load_dataset_df, dataset_id)
    try:
        _meta2 = storage.get_dataset_meta(dataset_id)
        _ver2 = _meta2.get("current_version", 0) if _meta2 else 0
    except:
        _ver2 = 0
    profile = await asyncio.to_thread(profile_dataframe, df, 5, True, dataset_id, _ver2)

    if not code:
        # Generate code
        intent = {"intent": "cleaning", "chart_type": "none", "columns": [], "aggregation": ""}
        code_res = await coder.generate_code(query, profile, intent)
        code = code_res["code"]
        explanation = code_res.get("explanation", "")
    else:
        explanation = "Applied from preview"

    # Validate and execute (single exec)
    from app.core.security import validate_code, SecurityError

    try:
        validate_code(code)
    except SecurityError as e:
        return {"success": False, "error": f"Security violation: {str(e)}", "code": code}

    exec_res = await asyncio.to_thread(executor.execute_code, code, df)
    if not exec_res["success"]:
        return {
            "success": False,
            "error": exec_res["error"],
            "code": code,
            "explanation": explanation,
        }

    after_df = exec_res.get("_after_df")
    if not isinstance(after_df, pd.DataFrame):
        # Fallback for cleaning codes that return shape/None (e.g., LLM shape) — try to infer cleaned df
        # If code contains drop_duplicates, assume intent was to dedup
        if "drop_duplicates" in code:
            try:
                after_df = df.drop_duplicates()
            except Exception:
                pass
        if not isinstance(after_df, pd.DataFrame):
            return {
                "success": False,
                "error": "Cleaning did not produce a DataFrame",
                "code": code,
            }

    # Validate
    validation = validate_clean_result(df, after_df)
    if not validation.get("valid", True):
        return {
            "success": False,
            "error": validation.get("reason", "Validation failed"),
            "code": code,
        }

    # Create version
    try:
        new_version = storage.create_version(
            dataset_id, after_df, op="clean", prompt=query, code=code
        )
    except Exception as e:
        return {"success": False, "error": f"Failed to save version: {str(e)}", "code": code}

    # Diff
    diff = diff_dataframes(df, after_df)
    diff["validation"] = validation

    # New profile (version-aware)
    try:
        _meta_n = storage.get_dataset_meta(dataset_id)
        _ver_n = _meta_n.get("current_version", 0) if _meta_n else 0
    except:
        _ver_n = 0
    new_profile = await asyncio.to_thread(profile_dataframe, after_df, 5, True, dataset_id, _ver_n)

    return {
        "success": True,
        "code": code,
        "explanation": explanation,
        "diff": diff,
        "new_version": new_version,
        "profile": new_profile,
        "preview": exec_res.get("result_json"),
        "chart": exec_res.get("chart_json"),
    }
