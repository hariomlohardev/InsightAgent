from typing import Dict, Any
import pandas as pd

from app.core import storage
from app.core.profiling import profile_dataframe
from app.core.wrangle import diff_dataframes, validate_clean_result
from app.agent import coder, executor
from app.agent.executor import dataframe_to_json, fig_to_json

async def preview_clean(dataset_id: str, query: str) -> Dict[str, Any]:
    """Preview cleaning without mutating. Returns diff, preview, code, etc."""
    df = storage.load_dataset_df(dataset_id)
    profile = profile_dataframe(df)
    
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
    
    # Execute on copy
    exec_res = executor.execute_code(code, df)
    
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
    
    # Get result df from exec
    # exec_res has result_json, but we need actual df for diff
    # Re-execute to get actual df? Or we can reconstruct from result_json? Better to exec again and capture df
    # For diff, we need before and after DataFrames
    # We can get after df by executing code and capturing result variable
    # Let's do a direct exec that captures result df
    try:
        # Use executor's safe globals to get after df
        from app.core.security import get_safe_globals
        import pandas as pd
        safe_globals = get_safe_globals(df)
        local_vars = {}
        # Need to handle timeout and security already validated
        exec(code, safe_globals, local_vars)
        after_df = local_vars.get("result")
        if not isinstance(after_df, pd.DataFrame):
            # Try to find any DataFrame
            for v in local_vars.values():
                if isinstance(v, pd.DataFrame):
                    after_df = v
                    break
            if not isinstance(after_df, pd.DataFrame):
                # Fallback: use result_json to reconstruct? Just use df
                after_df = df
    except Exception as e:
        after_df = df
        # Don't fail preview just because diff failed
    
    # Compute diff
    try:
        diff = diff_dataframes(df, after_df)
        validation = validate_clean_result(df, after_df)
        diff["validation"] = validation
    except Exception as e:
        diff = {"error": str(e)}
    
    # Prepare preview (after head)
    try:
        preview = dataframe_to_json(after_df.head(10), max_rows=10) if isinstance(after_df, pd.DataFrame) else exec_res.get("result_json")
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
    df = storage.load_dataset_df(dataset_id)
    profile = profile_dataframe(df)
    
    if not code:
        # Generate code
        intent = {"intent": "cleaning", "chart_type": "none", "columns": [], "aggregation": ""}
        code_res = await coder.generate_code(query, profile, intent)
        code = code_res["code"]
        explanation = code_res.get("explanation", "")
    else:
        explanation = "Applied from preview"
    
    # Validate and execute
    from app.core.security import validate_code, SecurityError
    try:
        validate_code(code)
    except SecurityError as e:
        return {"success": False, "error": f"Security violation: {str(e)}", "code": code}
    
    exec_res = executor.execute_code(code, df)
    if not exec_res["success"]:
        return {"success": False, "error": exec_res["error"], "code": code, "explanation": explanation}
    
    # Get after df
    try:
        from app.core.security import get_safe_globals
        safe_globals = get_safe_globals(df)
        local_vars = {}
        exec(code, safe_globals, local_vars)
        after_df = local_vars.get("result")
        if not isinstance(after_df, pd.DataFrame):
            for v in local_vars.values():
                if isinstance(v, pd.DataFrame):
                    after_df = v
                    break
            if not isinstance(after_df, pd.DataFrame):
                return {"success": False, "error": "Cleaning did not produce a DataFrame", "code": code}
    except Exception as e:
        return {"success": False, "error": f"Failed to capture result: {str(e)}", "code": code}
    
    # Validate
    validation = validate_clean_result(df, after_df)
    if not validation.get("valid", True):
        return {"success": False, "error": validation.get("reason", "Validation failed"), "code": code}
    
    # Create version
    try:
        new_version = storage.create_version(dataset_id, after_df, op="clean", prompt=query, code=code)
    except Exception as e:
        return {"success": False, "error": f"Failed to save version: {str(e)}", "code": code}
    
    # Diff
    diff = diff_dataframes(df, after_df)
    diff["validation"] = validation
    
    # New profile
    new_profile = profile_dataframe(after_df)
    
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
