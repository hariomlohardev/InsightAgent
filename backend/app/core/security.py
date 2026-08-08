import ast

# Modules that generated code is allowed to import/use
ALLOWED_MODULES = {"pandas", "pd", "numpy", "np", "plotly", "plotly.express", "plotly.graph_objects", "px", "go", "duckdb", "datetime", "json", "re", "math"}

# Explicitly blocked imports - any attempt is rejected
BLOCKED_MODULES = {"os", "sys", "subprocess", "socket", "shutil", "pathlib", "importlib", "builtins", "__builtins__", "eval", "exec"}

BLOCKED_NAMES = {"eval", "exec", "compile", "__import__", "open", "input", "exit", "quit", "help", "globals", "locals", "vars", "dir", "getattr", "setattr", "delattr", "hasattr"}

BLOCKED_ATTRS = {"__class__", "__bases__", "__subclasses__", "__dict__", "__weakref__", "__mro__", "__globals__", "__code__", "__closure__"}

class SecurityError(Exception):
    pass

def validate_code(code: str) -> None:
    """
    Parse code AST and ensure no dangerous operations.
    Raises SecurityError if violation.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SecurityError(f"Syntax error: {e}")

    for node in ast.walk(tree):
        # Block imports of dangerous modules
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in BLOCKED_MODULES:
                    raise SecurityError(f"Import of '{alias.name}' is not allowed")
                # Allow only known safe modules
                # But be lenient - allow pandas, numpy, plotly, duckdb etc, block only dangerous
                # So we don't enforce strict allowlist for imports, just blocklist

        if isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top in BLOCKED_MODULES:
                    raise SecurityError(f"Import from '{node.module}' is not allowed")

        # Block dangerous function calls
        if isinstance(node, ast.Call):
            # e.g., eval(...), open(...), __import__(...)
            if isinstance(node.func, ast.Name):
                if node.func.id in BLOCKED_NAMES:
                    raise SecurityError(f"Call to '{node.func.id}' is not allowed")
            # e.g., os.system
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in BLOCKED_NAMES or node.func.attr in BLOCKED_ATTRS:
                    raise SecurityError(f"Attribute call '{node.func.attr}' is not allowed")
                # Block things like subprocess.call
                if isinstance(node.func.value, ast.Name):
                    if node.func.value.id in BLOCKED_MODULES:
                        raise SecurityError(f"Call on blocked module '{node.func.value.id}' is not allowed")

        # Block dangerous attributes
        if isinstance(node, ast.Attribute):
            if node.attr in BLOCKED_ATTRS:
                raise SecurityError(f"Access to attribute '{node.attr}' is not allowed")

        # Block usage of blocked names directly
        if isinstance(node, ast.Name):
            if node.id in BLOCKED_MODULES:
                # Allow if it's just a variable name like 'os' used as column? But be strict for imports
                pass

def get_safe_globals(df):
    """Build safe globals dict for exec."""
    import pandas as pd
    import numpy as np
    import plotly.express as px
    import plotly.graph_objects as go
    import duckdb
    
    safe_builtins = {
        "len": len,
        "range": range,
        "enumerate": enumerate,
        "zip": zip,
        "list": list,
        "dict": dict,
        "set": set,
        "tuple": tuple,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "sum": sum,
        "min": min,
        "max": max,
        "sorted": sorted,
        "abs": abs,
        "round": round,
        "print": print,
        "__builtins__": {
            "len": len,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "sum": sum,
            "min": min,
            "max": max,
            "sorted": sorted,
            "abs": abs,
            "round": round,
            "print": print,
        }
    }
    
    return {
        "df": df,
        "pd": pd,
        "np": np,
        "px": px,
        "go": go,
        "duckdb": duckdb,
        **safe_builtins,
    }
