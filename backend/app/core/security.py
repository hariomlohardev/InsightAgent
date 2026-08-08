import ast

# Modules that generated code is allowed to import/use (for reference, not enforced as strict allowlist)
ALLOWED_MODULES = {
    "pandas",
    "pd",
    "numpy",
    "np",
    "plotly",
    "plotly.express",
    "plotly.graph_objects",
    "px",
    "go",
    "duckdb",
    "datetime",
    "json",
    "re",
    "math",
    "statsforecast",
    "prophet",
}

# Explicitly blocked imports - any attempt is rejected. Extended for L1.4 hardening.
BLOCKED_MODULES = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "importlib",
    "builtins",
    "__builtins__",
    "eval",
    "exec",
    "time",
    "threading",
    "multiprocessing",
    "concurrent",
    "asyncio",
    "pty",
    "tty",
    "ctypes",
    "cffi",
    "signal",
    "gc",
    "inspect",
    "ast",
    "dis",
    "code",
    "codeop",
    "compileall",
    "py_compile",
    "pickle",
    "marshal",
    "shelve",
    "dbm",
    "sqlite3",
    "http",
    "urllib",
    "ftplib",
    "smtplib",
    "poplib",
    "imaplib",
}

BLOCKED_NAMES = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "input",
    "exit",
    "quit",
    "help",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "hasattr",
    "breakpoint",
    "memoryview",
    "bytearray",
    "bytes",
    "execfile",
    "file",
    "raw_input",
}

BLOCKED_ATTRS = {
    "__class__",
    "__bases__",
    "__subclasses__",
    "__dict__",
    "__weakref__",
    "__mro__",
    "__globals__",
    "__code__",
    "__closure__",
    "__self__",
    "__module__",
    "__annotations__",
    "__wrapped__",
    "__qualname__",
    "gi_frame",
    "gi_code",
    "cr_frame",
    "cr_code",
}


class SecurityError(Exception):
    pass


def validate_code(code: str) -> None:
    """
    Parse code AST and ensure no dangerous operations.
    Raises SecurityError if violation.
    Hardened for L1.4: blocks more modules, checks ImportFrom, Call, Attribute, and Name.
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
                # Also block 'import time' even if not in top? Already covered
                # Enforce that import is at least not empty

        if isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top in BLOCKED_MODULES:
                    raise SecurityError(f"Import from '{node.module}' is not allowed")
                # Block 'from os import path' etc
                for alias in node.names:
                    if alias.name in BLOCKED_NAMES or alias.name in BLOCKED_ATTRS:
                        raise SecurityError(
                            f"Import of '{alias.name}' from '{node.module}' is not allowed"
                        )

        # Block dangerous function calls
        if isinstance(node, ast.Call):
            # e.g., eval(...), open(...), __import__(...)
            if isinstance(node.func, ast.Name):
                if node.func.id in BLOCKED_NAMES:
                    raise SecurityError(f"Call to '{node.func.id}' is not allowed")
                if node.func.id in BLOCKED_MODULES:
                    raise SecurityError(f"Call on blocked module '{node.func.id}' is not allowed")
            # e.g., os.system, subprocess.call, pathlib.Path
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in BLOCKED_NAMES or node.func.attr in BLOCKED_ATTRS:
                    raise SecurityError(f"Attribute call '{node.func.attr}' is not allowed")
                # Block things like subprocess.call, os.system, sys.exit
                if isinstance(node.func.value, ast.Name):
                    if node.func.value.id in BLOCKED_MODULES:
                        raise SecurityError(
                            f"Call on blocked module '{node.func.value.id}' is not allowed"
                        )
                # Also block nested like os.path.join
                if isinstance(node.func.value, ast.Attribute):
                    # e.g., os.path.join
                    cur = node.func.value
                    while isinstance(cur, ast.Attribute):
                        cur = cur.value
                    if isinstance(cur, ast.Name) and cur.id in BLOCKED_MODULES:
                        raise SecurityError(f"Call on blocked module '{cur.id}' is not allowed")

        # Block dangerous attributes
        if isinstance(node, ast.Attribute):
            if node.attr in BLOCKED_ATTRS:
                raise SecurityError(f"Access to attribute '{node.attr}' is not allowed")
            if node.attr in BLOCKED_NAMES:
                # e.g., x.eval, x.exec - but these are less risky, still block if matches
                pass

        # Block 'import time' via Name usage? Already via Import, but also block direct __import__('os')
        if isinstance(node, ast.Name):
            if node.id == "__import__":
                raise SecurityError(f"Use of '__import__' is not allowed")
            # Don't block variable named 'os' used as column name; only block if used as value in Call/Attribute already handled


def get_safe_globals(df):
    """Build safe globals dict for exec. Limited but includes __import__ for duckdb internal use (user code still blocked via AST)."""
    import pandas as pd
    import numpy as np
    import plotly.express as px
    import plotly.graph_objects as go

    try:
        import duckdb
    except ImportError:
        duckdb = None

    # Safe builtins - include __import__ for libraries (AST blocks user from using it with dangerous modules)
    safe_builtins_dict = {
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
        "isinstance": isinstance,
        "issubclass": issubclass,
        "hasattr": hasattr,
        "getattr": getattr,
        "__import__": __import__,
    }

    safe_globals = {
        "df": df,
        "pd": pd,
        "np": np,
        "px": px,
        "go": go,
    }
    if duckdb is not None:
        safe_globals["duckdb"] = duckdb
    # Analytics helpers (L5) — expose for code generation without needing import
    try:
        from app.core.analytics.why import analyze_why, what_if
        from app.core.analytics.outliers import find_outliers
        from app.core.analytics.segments import segment
        from app.core.analytics.forecast import forecast

        safe_globals["analyze_why"] = analyze_why
        safe_globals["what_if"] = what_if
        safe_globals["find_outliers"] = find_outliers
        safe_globals["segment"] = segment
        safe_globals["forecast"] = forecast
    except Exception:
        pass
    # Add safe builtins
    safe_globals.update(safe_builtins_dict)
    # Provide __builtins__ as limited dict
    safe_globals["__builtins__"] = safe_builtins_dict

    return safe_globals
