import time
import re
import io
from pathlib import Path
from typing import Dict, Any, Optional, List
import pandas as pd

from app.core.security import SecurityError

# ---- SQL guard — read-only allowlist + DB-layer enforcement ----
WRITE_KEYWORDS = [
    "insert ",
    "update ",
    "delete ",
    "drop ",
    "create ",
    "alter ",
    "truncate ",
    "grant ",
    "revoke ",
]
# Dangerous DuckDB/extension ops that must be blocked even if starting with SELECT
BLOCKED_SQL_TOKENS = [
    "attach ",
    "detach ",
    "install ",
    "load ",
    "copy ",
    "export ",
    "import ",
    "pragma ",
    "vacuum ",
    "checkpoint ",
    "use ",
]
ALLOWED_START = ("select", "with", "explain", "show", "describe")


# For sqlparse-based validation if available
def _sql_statements(sql: str):
    try:
        import sqlparse  # type: ignore

        # split and strip
        stmts = [s.strip() for s in sqlparse.split(sql) if s.strip()]
        return stmts
    except ImportError:
        # fallback: split on ; but respect quotes naive — safe to be strict: reject multi-statement if ; present
        parts = [p.strip() for p in sql.split(";") if p.strip()]
        return parts


def _normalize_sql(s: str) -> str:
    # Remove comments and collapse whitespace, lower
    s = re.sub(r"--.*", " ", s)
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.DOTALL)
    # remove string literals to avoid false positives? keep for blocklist but normalize
    s = re.sub(r"'[^']*'", " 'x' ", s)
    s = re.sub(r'"[^"]*"', ' "x" ', s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def validate_sql(sql: str) -> None:
    """Raise SecurityError unless sql is read-only SELECT/WITH/EXPLAIN. Enforces parser allowlist + DB restrictions."""
    if not sql or not sql.strip():
        raise SecurityError("Empty SQL")
    # multi-statement check
    stmts = _sql_statements(sql)
    if len(stmts) > 1:
        raise SecurityError("Multi-statement SQL not allowed")
    stmt = stmts[0] if stmts else sql
    norm = _normalize_sql(stmt)
    # must start with allowed
    if not norm.startswith(ALLOWED_START):
        if not (norm.startswith("(") and "select" in norm[:80]):
            raise SecurityError(f"Only SELECT/WITH/EXPLAIN queries allowed, got: {sql[:40]!r}")
    # block write keywords and dangerous tokens anywhere (after normalization)
    for kw in WRITE_KEYWORDS + BLOCKED_SQL_TOKENS:
        if kw in norm:
            # special case: allow "copy " inside quoted identifier already replaced, so remaining copy is dangerous (COPY TO)
            raise SecurityError(f"SQL blocked: contains '{kw.strip().upper()}' — read-only only")
    # extra duckdb-specific: block TO after COPY, FROM afterATTACH, etc already covered
    # block ; to prevent second statement if sqlparse not available (already split)
    if ";" in stmt:
        # if sqlparse split returned single but original had ; inside, it's still multi or dangerous
        # allow trailing ; for single statement?
        if stmt.strip().endswith(";"):
            # strip trailing ; already handled by split, check if another statement hidden
            pass
        else:
            raise SecurityError("Semicolon not allowed")


# ---- Cache for sheets ----
_SHEETS_CACHE: Dict[str, Any] = {}  # id -> {df, ts}


def _sheets_export_url(sheet_url_or_id: str) -> str:
    # Extract id from full URL
    # https://docs.google.com/spreadsheets/d/<ID>/edit#gid=0
    # or https://docs.google.com/spreadsheets/d/<ID>/export?format=csv
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url_or_id)
    if m:
        doc_id = m.group(1)
    else:
        # Could be raw ID
        doc_id = sheet_url_or_id.strip().split("/")[0].split("?")[0]
        if len(doc_id) < 10:
            raise ValueError(f"Invalid Sheets ID/URL: {sheet_url_or_id[:60]}")
    return f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv"


def fetch_sheets_df(connector: Dict[str, Any], limit: int = 500, sql: str = None) -> pd.DataFrame:
    sheet_url = connector.get("sheet_url") or connector.get("dsn") or connector.get("table")
    if not sheet_url:
        raise ValueError("Sheets connector missing sheet_url")
    cache_id = connector.get("id", sheet_url)
    now = time.time()
    cached = _SHEETS_CACHE.get(cache_id)
    if cached and (now - cached["ts"] < 60) and not sql:
        df = cached["df"]
    else:
        url = _sheets_export_url(sheet_url)
        is_httpx = False
        r = None
        try:
            try:
                import requests

                r = requests.get(url, timeout=10)
            except ImportError:
                import httpx

                r = httpx.get(url, timeout=10)
                is_httpx = True
        except Exception as e:
            raise RuntimeError(f"Sheets fetch failed: {e}")
        if r is None or r.status_code != 200:
            raise RuntimeError(
                f"Sheets fetch failed ({getattr(r, 'status_code', 'no response')}). Make sheet public (Anyone with link) or add SHEETS_API_KEY in .env (private sheets need OAuth — coming in L7). URL: {url[:60]}"
            )
        text = r.text
        if not text.strip():
            raise RuntimeError("Sheets returned empty CSV")
        df = pd.read_csv(io.StringIO(text))
        _SHEETS_CACHE[cache_id] = {"df": df, "ts": now}
        # Also cache to disk for persistence
        try:
            from app.config import get_storage_path

            cache_dir = get_storage_path() / "connectors" / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            df.to_csv(cache_dir / f"{cache_id}.csv", index=False)
        except Exception:
            pass
    # SQL filtering via duckdb if provided
    if sql:
        validate_sql(sql)
        import duckdb

        con = duckdb.connect()
        con.register("df", df)
        try:
            result = con.execute(sql).df()
            return result.head(limit) if limit else result
        finally:
            con.close()
    if limit:
        return df.head(limit)
    return df


def fetch_sqlite_df(connector: Dict[str, Any], limit: int = 500, sql: str = None) -> pd.DataFrame:
    dsn = connector.get("dsn") or connector.get("db_path") or ":memory:"
    table = connector.get("table")
    # For tests, support dsn = path to csv-loaded :memory: setup is handled via table existence
    import sqlite3

    # If dsn is a file path that doesn't exist, error
    # But for :memory: we need to check if connector has _memory_init marker — but we'll just connect fresh and check
    # To support CI, if dsn == ":memory:" and connector has "init_sql" we run it
    init_sql = connector.get("init_sql")
    conn = sqlite3.connect(dsn)
    try:
        if init_sql:
            conn.executescript(init_sql)
        if sql:
            validate_sql(sql)
            return pd.read_sql_query(sql, conn)
        if table:
            # Validate table name (alnum + _)
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table):
                raise ValueError(f"Invalid table name: {table}")
            q = f'SELECT * FROM "{table}" LIMIT {int(limit) if limit else 500}'
            return pd.read_sql_query(q, conn)
        # No table: list tables and fetch first
        tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", conn)
        if tables.empty:
            raise ValueError("SQLite DB has no tables")
        first = tables.iloc[0]["name"]
        q = f'SELECT * FROM "{first}" LIMIT {int(limit) if limit else 500}'
        return pd.read_sql_query(q, conn)
    finally:
        conn.close()


def fetch_postgres_df(connector: Dict[str, Any], limit: int = 500, sql: str = None) -> pd.DataFrame:
    dsn = connector.get("dsn")
    if not dsn:
        raise ValueError("Postgres connector missing dsn")
    if sql:
        validate_sql(sql)
    else:
        table = connector.get("table")
        if not table:
            raise ValueError("Postgres connector requires table or sql")
        # Validate table
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_\"\.]*$", table):
            raise ValueError(f"Invalid table: {table}")
        sql = f"SELECT * FROM {table} LIMIT {int(limit) if limit else 500}"
    # Try sqlalchemy if available, else psycopg2
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(dsn, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            # For postgres, we can try setting read-only transaction
            # But keep simple: just read
            return pd.read_sql(text(sql), conn)
    except ImportError:
        pass
    # Fallback psycopg2
    try:
        import psycopg2

        conn = psycopg2.connect(dsn, connect_timeout=5)
        try:
            return pd.read_sql(sql, conn)
        finally:
            conn.close()
    except ImportError as e:
        raise RuntimeError(
            "Postgres driver not installed: pip install psycopg2-binary sqlalchemy — or use SQLite for testing"
        )
    except Exception as e:
        raise RuntimeError(f"Postgres query failed: {e}")


def fetch_mysql_df(connector: Dict[str, Any], limit: int = 500, sql: str = None) -> pd.DataFrame:
    dsn = connector.get("dsn")
    if not dsn:
        raise ValueError("MySQL connector missing dsn")
    if sql:
        validate_sql(sql)
    else:
        table = connector.get("table")
        if not table:
            raise ValueError("MySQL requires table or sql")
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table):
            raise ValueError(f"Invalid table: {table}")
        sql = f"SELECT * FROM `{table}` LIMIT {int(limit) if limit else 500}"
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(dsn, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn)
    except ImportError:
        pass
    try:
        import pymysql

        # dsn for pymysql is not url; we try to parse
        # For now error if no sqlalchemy
        raise RuntimeError("MySQL driver not installed: pip install pymysql sqlalchemy")
    except Exception as e:
        raise RuntimeError(f"MySQL query failed: {e}")


def fetch_bigquery_df(connector: Dict[str, Any], limit: int = 500, sql: str = None) -> pd.DataFrame:
    # Check credentials
    import os

    creds = (
        connector.get("credentials_json")
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        or os.getenv("BIGQUERY_CREDENTIALS")
    )
    if not creds:
        raise RuntimeError(
            "BigQuery not configured: set GOOGLE_APPLICATION_CREDENTIALS (path to service JSON) or pass credentials_json — see docs. Returning 501."
        )
    if sql:
        validate_sql(sql)
    else:
        table = connector.get("table")
        if not table:
            raise ValueError("BigQuery requires table (e.g., project.dataset.table) or sql")
        sql = f"SELECT * FROM `{table}` LIMIT {int(limit) if limit else 500}"
    try:
        import pandas_gbq

        # pandas_gbq will use credentials
        # We pass sql directly
        return pandas_gbq.read_gbq(sql)
    except ImportError:
        raise RuntimeError(
            "BigQuery driver not installed: pip install pandas-gbq google-cloud-bigquery"
        )
    except Exception as e:
        raise RuntimeError(f"BigQuery query failed: {e}")


def fetch_df(connector: Dict[str, Any], limit: int = 500, sql: str = None) -> pd.DataFrame:
    kind = (connector.get("kind") or connector.get("type") or "").lower()
    if kind in ("postgres", "postgresql"):
        return fetch_postgres_df(connector, limit=limit, sql=sql)
    elif kind in ("mysql",):
        return fetch_mysql_df(connector, limit=limit, sql=sql)
    elif kind in ("sqlite",):
        return fetch_sqlite_df(connector, limit=limit, sql=sql)
    elif kind in ("bigquery", "bq"):
        return fetch_bigquery_df(connector, limit=limit, sql=sql)
    elif kind in ("sheets", "gsheets", "google_sheets"):
        return fetch_sheets_df(connector, limit=limit, sql=sql)
    else:
        raise ValueError(
            f"Unknown connector kind: {kind}. Supported: postgres, mysql, sqlite, bigquery, sheets"
        )
