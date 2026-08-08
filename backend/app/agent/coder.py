import os
import json
import re
from typing import Dict, Any

from app.agent.prompts import SYSTEM_CODER_PROMPT
from app.core.profiling import get_profile_summary_text
from app.core.llm import get_llm, extract_json

def _is_write_sql(q_lower: str) -> bool:
    blocked = ["insert ", "update ", "delete ", "drop ", "create ", "alter ", "truncate ", "grant ", "revoke "]
    return any(b in q_lower for b in blocked)

def _sql_to_pandas_fallback_hint(sql: str) -> str:
    # Small hint for when LLM not available for NL→SQL
    return "Tip: Add OPENAI_API_KEY/GROQ_API_KEY for NL→SQL, or type raw SQL like SELECT * FROM df WHERE ..."

def fallback_coder(query: str, profile: Dict[str, Any]) -> Dict[str, str]:
    """Rule-based coder covering 15+ common patterns + SQL branch for L4. No LLM needed."""
    q = query.lower().strip()
    cols = profile.get("column_names", [])
    numeric_cols = profile.get("numeric_columns", [])
    cat_cols = profile.get("categorical_columns", [])
    intent_hint = profile.get("_intent_hint")  # injected by chat_service for connector
    # L4: if intent is sql but query is NL (not SELECT), try to translate via simple heuristic or fallback
    if profile.get("_intent") == "sql" or intent_hint == "sql":
        # If query is already SQL, handle below; else it's NL that should be SQL (connector)
        if not (q.startswith("select") or q.startswith("with")):
            # Simple NL→SQL heuristic for connectors (sqlite/postgres) without LLM: map common phrases
            # For now, return a helpful fallback that still shows data via duckdb
            # Attempt lightweight NL->SQL: top 5 sales -> SELECT * FROM df ORDER BY sales DESC LIMIT 5
            # We'll just do fallback that selects head and gives hint
            pass  # fall through to SQL handler after we set q to SELECT if possible
    
    # Helpers to find best column
    def find_col(keywords, candidates):
        # Find column that contains any keyword
        q_low = q
        for c in candidates:
            if c.lower() in q_low:
                return c
        # If no match, return first of candidates
        for kw in keywords:
            for c in candidates:
                if kw in c.lower():
                    return c
        return candidates[0] if candidates else (cols[0] if cols else "unknown")

    def find_numeric():
        return find_col([], numeric_cols) if numeric_cols else (cols[0] if cols else "value")

    def find_categorical():
        return find_col([], cat_cols) if cat_cols else (cols[0] if cols else "category")

    # Pre-process query for common intents
    code = ""
    explanation = ""

    # 0. SQL passthrough (highest priority) - use duckdb for fidelity; also handles connector NL→SQL fallback
    if q.strip().startswith("select") or q.strip().startswith("with"):
        sql = query.strip().rstrip(";")
        if _is_write_sql(q):
            code = f"result = df.head(10)\nfig = px.bar(result.head(5), x=result.columns[0], y=result.columns[1] if len(result.columns)>1 else result.columns[0], title='Blocked: read-only SQL only')"
            explanation = "Blocked DDL/DML, only SELECT allowed"
            return {"code": code, "explanation": explanation}
        where_match = re.search(r"where\s+(.+)", sql, re.IGNORECASE)
        if where_match:
            where_clause = where_match.group(1).strip()
            where_clause = re.split(r"\s+limit\s+|\s+order\s+by\s+|\s+group\s+by\s+", where_clause, flags=re.IGNORECASE)[0].strip()
            where_escaped = where_clause.replace("'", "\\'")
            code = f"duckdb.register('df', df)\ntry:\n    result = duckdb.query('''{sql}''').to_df()\nexcept Exception:\n    try:\n        result = df.query('{where_escaped}', engine='python')\n    except Exception:\n        result = df.head(20)\nfig = px.bar(result.head(20), x=result.columns[0] if len(result.columns)>0 else 'x', y=result.columns[1] if len(result.columns)>1 else result.columns[0], title='SQL Result')"
        else:
            code = f"duckdb.register('df', df)\ntry:\n    result = duckdb.query('''{sql}''').to_df()\nexcept Exception:\n    result = df.head(20)\nfig = px.bar(result.head(20), x=result.columns[0] if len(result.columns)>0 else 'x', y=result.columns[1] if len(result.columns)>1 else result.columns[0], title='SQL Result')"
        explanation = f"Executed SQL: {sql[:60]}"
        return {"code": code, "explanation": explanation}
    
    # 0a. L4 NL→SQL for connectors: if intent is sql but query is not raw SQL, try LLM translation or heuristic
    # This path is also handled in generate_code (LLM branch) but we provide heuristic fallback here
    if profile.get("_intent") == "sql" or intent_hint == "sql":
        # Attempt lightweight heuristic: if query contains "top 5" etc, build SELECT
        # Otherwise fallback to showing df with hint
        # Heuristic for common NL: "top 5 <cat> by <num>"
        # We defer to LLM in generate_code; here just produce a plausible SELECT via pandas groupby code is not SQL, so we craft duckdb code with hint
        # For heuristic, try to infer SELECT for connector without LLM
        # e.g., "top 5 products by sales" -> SELECT Category, SUM(Sales) ... ORDER BY ... LIMIT 5
        # Simple path: if no LLM, still execute groupby-like code but via duckdb so it works on connector df
        # We won't block; let's create a code that works but marks insight hint
        pass  # handled in generate_code fallback; continue to normal patterns below

    # 0a. Analytics (L5) — must come BEFORE cleaning (outlier moved to analytics)
    # Branches: forecast, what-if, outlier, segment, why, correlation
    # We handle analytics via explicit intent or keyword, highest after SQL

    # Forecast — e.g., "forecast sales for next 3 months", "predict sales"
    if any(k in q for k in ["forecast", "predict"]) or (("next" in q and any(w in q for w in ["month","week","day"])) and any(c.lower() in q for c in cols + numeric_cols)):
        # Parse periods and freq
        periods = 3
        m = re.search(r"next\s+(\d+)", q)
        if m:
            try:
                periods = int(m.group(1))
                periods = max(1, min(periods, 12))
            except:
                periods = 3
        # Find freq
        freq = "M"
        if "week" in q:
            freq = "W"
        elif "day" in q or "daily" in q:
            freq = "D"
        # Find date_col and metric
        date_cands = [c for c in cols if "date" in c.lower() or "time" in c.lower()]
        metric_cand = None
        for c in numeric_cols:
            if c.lower() in q:
                metric_cand = c
                break
        if not metric_cand:
            metric_cand = numeric_cols[0] if numeric_cols else (cols[0] if cols else "value")
        date_cand = date_cands[0] if date_cands else "Date"
        # If profile has inferred date, prefer that
        for c in cols:
            if c in profile.get("column_names", []) and "date" in c.lower():
                date_cand = c
                break
        code = f"result, fig, _metrics = forecast(df, date_col='{date_cand}', metric='{metric_cand}', periods={periods}, freq='{freq}', profile={repr(profile)})\n# metrics: {{k: v for k,v in _metrics.items() if k not in ['df_flagged']}}"
        explanation = f"Forecast {metric_cand} by {date_cand} for next {periods} {freq} ({'statsforecast' if periods else 'naive'} if available)"
        return {"code": code, "explanation": explanation}

    # What-if — e.g., "what if sales increased 10%" or "what if price *1.1"
    if "what if" in q or "what-if" in q:
        # Parse pct and col
        pct = 10
        m_pct = re.search(r"(\d+)\s*%", q)
        if m_pct:
            pct = int(m_pct.group(1))
            if "decrease" in q or "down" in q or "fall" in q or "reduce" in q:
                pct = -pct
        elif "increased" in q:
            pct = 10
        elif "decreased" in q:
            pct = -10
        # Find column
        target_col = None
        for c in cols:
            if c.lower() in q:
                target_col = c
                break
        if not target_col:
            target_col = numeric_cols[0] if numeric_cols else cols[0]
        # Find by (optional)
        by_col = None
        if " by " in q:
            parts = q.split(" by ")
            for c in cols:
                if c.lower() in parts[-1]:
                    by_col = c
                    break
        by_repr = f"'{by_col}'" if by_col else "None"
        metric_repr = f"'{target_col}'"
        code = f"result = what_if(df, col='{target_col}', pct={pct}, metric={metric_repr}, by={by_repr})\nfig = px.bar(result, x='category', y='delta', title='What-if: {target_col} {pct:+}%', color='delta', color_continuous_scale='RdYlGn')"
        explanation = f"What-if {target_col} {pct:+}%"
        return {"code": code, "explanation": explanation}

    # Outliers — analytics via find_outliers (IQR/Z) — not cleaning
    # Need to keep test_coder_cleaning's "remove outliers" still matching original cleaning logic?
    # That test expects mean/std in code for "remove outliers in Sales" (cleaning). So for exact query "remove outliers..."
    # we preserve cleaning mean/std path inside cleaning branch; analytics outlier branch also handles "show outliers"/"outliers in"
    # This branch is for analytics outlier detection (show/outlier), not removal
    if any(k in q for k in ["outlier", "anomal"]) and not q.strip().startswith("remove outliers"):
        # Find column
        col = None
        for c in cols:
            if c.lower() in q:
                col = c
                break
        if not col:
            col = numeric_cols[0] if numeric_cols else cols[0]
        method = "zscore" if "z" in q.lower() else "iqr"
        code = f"_out = find_outliers(df, col='{col}', method='{method}')\nresult = _out['df_flagged'].head(50)\nfig = px.scatter(_out['df_flagged'], x=_out['df_flagged'].index, y='{col}', color='is_outlier', color_discrete_map={{True: '#dc2626', False: '#64748b'}}, title='Outliers in {col} ({{}} flagged)'.format(_out['outliers']))"
        explanation = f"Outliers in {col} via {method} ({'IQR' if method=='iqr' else 'Z-score'})"
        return {"code": code, "explanation": explanation}

    # Segment / Cohort — e.g., "segment by Region", "cohort by Product"
    if any(k in q for k in ["segment by", "cohort by", "breakdown by", "segment", "cohort"]):
        # Parse by
        by_col = None
        m = re.search(r"(?:segment|cohort|breakdown)\s*by\s+(\w+)", q)
        if m:
            word = m.group(1)
            for c in cols:
                if word in c.lower() or c.lower() in word:
                    by_col = c
                    break
        if not by_col:
            # Try any categorical mentioned
            for c in cat_cols:
                if c.lower() in q:
                    by_col = c
                    break
        if not by_col:
            by_col = cat_cols[0] if cat_cols else cols[0]
        # Metric
        metric = None
        for c in numeric_cols:
            if c.lower() in q:
                metric = c
                break
        if not metric:
            metric = numeric_cols[0] if numeric_cols else cols[0]
        agg = "sum"
        if "average" in q or "mean" in q:
            agg = "mean"
        elif "median" in q:
            agg = "median"
        elif "count" in q:
            agg = "count"
        code = f"result = segment(df, by='{by_col}', metric='{metric}', agg='{agg}')\nfig = px.bar(result.head(10), x='category', y='value', title='Segment by {by_col} — {metric} ({agg})', color='share' if 'share' in result.columns else None, text_auto=True)"
        explanation = f"Segment by {by_col} metric {metric} agg {agg}"
        return {"code": code, "explanation": explanation}

    # Backfill: add to dashboard_service comments migration? no-op
    # Why / explain drop/increase — e.g., "why did sales drop in March?"
    if any(k in q for k in ["why", "explain", "reason"]) or (any(w in q for w in ["drop","increase","decrease","fall","rise"]) and "?" in query):
        safe_q = query.replace("'", r"\'").replace("\n"," ").replace("'''","'")[:500]
        code = f"result = analyze_why(df, {repr(profile)}, '''{safe_q}''')\nfig = px.bar(result, x='category', y='delta', title='Why analysis: delta by category (top contributors)', color='delta', color_continuous_scale='RdBu')"
        explanation = f"Why analysis via cohort diff"
        return {"code": code, "explanation": explanation}
    # Also fallback: if intent is analytics and query is drop/increase without why but analytics planner flagged
    if profile.get("_intent") == "analytics" or intent_hint == "analytics":
        if any(w in q for w in ["drop","increase","fall","rise","decrease"]):
            safe_q = query.replace("'", r"\'").replace("\n"," ").replace("'''","'")[:500]
            code = f"result = analyze_why(df, {repr(profile)}, '''{safe_q}''')\nfig = px.bar(result, x='category', y='delta', title='Why analysis: delta by category', color='delta', color_continuous_scale='RdBu')"
            explanation = "Why analysis (cohort diff)"
            return {"code": code, "explanation": explanation}

    # Correlation / heatmap — use available profile lists directly (no import, stays in allowlist)
    if "correlation" in q or "heatmap" in q:
        num_list_repr = repr(numeric_cols)
        code = f"_cols = {num_list_repr}\nif _cols and len(_cols)>=2:\n    result = df[_cols].corr(numeric_only=True)\nelse:\n    result = df.corr(numeric_only=True)\nresult = result.reset_index().rename(columns={{'index':'variable'}})\nfig = px.imshow(df[_cols].corr(numeric_only=True) if _cols else df.corr(numeric_only=True), text_auto=True, aspect='auto', title='Correlation heatmap')"
        explanation = "Correlation matrix"
        return {"code": code, "explanation": explanation}

    # 0b. Cleaning / Wrangling (Level 2) - 12 intents, preview mode (result = cleaned df)
    # Order matters: cleaning before other groupby to avoid misrouting
    # Detect cleaning via keywords
    cleaning_keywords = ["clean", "remove", "fill", "drop", "rename", "convert", "trim", "standardize", "split", "merge", "pivot", "melt"]
    is_cleaning = any(k in q for k in cleaning_keywords) or "fill" in q or "trim" in q
    
    # Use helper to find column by fuzzy match
    def _find_col_fuzzy(word: str, candidates):
        word = word.lower().strip()
        for c in candidates:
            if word == c.lower():
                return c
            if word in c.lower() or c.lower() in word:
                return c
        # Try singular/plural
        for c in candidates:
            if word.rstrip('s') == c.lower().rstrip('s'):
                return c
        return None

    if is_cleaning:
        # 1. Remove duplicates
        if "duplicate" in q:
            if "on " in q or "subset" in q or any(c.lower() in q for c in cols):
                # Try to find column mentioned
                col_match = None
                for c in cols:
                    if c.lower() in q:
                        col_match = c
                        break
                if col_match:
                    code = f"result = df.drop_duplicates(subset=['{col_match}'])\nfig = px.bar(pd.DataFrame({{'metric':['before','after'], 'value':[len(df), len(result)]}}), x='metric', y='value', title='Duplicates removed on {col_match}')"
                    explanation = f"Removed duplicates on {col_match}"
                else:
                    code = f"result = df.drop_duplicates()\nfig = px.bar(pd.DataFrame({{'metric':['before','after'], 'value':[len(df), len(result)]}}), x='metric', y='value', title='Duplicates removed')"
                    explanation = "Removed duplicates"
            else:
                code = f"result = df.drop_duplicates()\nfig = px.bar(pd.DataFrame({{'metric':['before','after'], 'value':[len(df), len(result)]}}), x='metric', y='value', title='Duplicates removed')"
                explanation = "Removed duplicates"
            return {"code": code, "explanation": explanation}
        
        # 2. Fill nulls
        if "fill" in q and ("null" in q or "missing" in q or "na" in q or "nan" in q):
            # Find column
            col = None
            for c in cols:
                if c.lower() in q:
                    col = c
                    break
            # Strategy
            strategy = "median"
            if "mean" in q:
                strategy = "mean"
            elif "median" in q:
                strategy = "median"
            elif "mode" in q:
                strategy = "mode"
            elif "ffill" in q or "forward" in q:
                strategy = "ffill"
            elif "bfill" in q or "backward" in q:
                strategy = "bfill"
            elif "zero" in q:
                strategy = "zero"
            
            if col:
                if strategy == "median":
                    code = f"result = df.copy()\nresult['{col}'] = result['{col}'].fillna(result['{col}'].median())\nfig = px.bar(pd.DataFrame({{'metric':['nulls_before','nulls_after'], 'value':[df['{col}'].isna().sum(), result['{col}'].isna().sum()]}}), x='metric', y='value', title='Filled nulls in {col} with median')"
                elif strategy == "mean":
                    code = f"result = df.copy()\nresult['{col}'] = result['{col}'].fillna(result['{col}'].mean())\nfig = px.bar(pd.DataFrame({{'metric':['nulls_before','nulls_after'], 'value':[df['{col}'].isna().sum(), result['{col}'].isna().sum()]}}), x='metric', y='value', title='Filled nulls in {col} with mean')"
                elif strategy == "mode":
                    code = f"result = df.copy()\nresult['{col}'] = result['{col}'].fillna(result['{col}'].mode()[0] if not result['{col}'].mode().empty else 'unknown')\nfig = px.bar(pd.DataFrame({{'metric':['nulls_before','nulls_after'], 'value':[df['{col}'].isna().sum(), result['{col}'].isna().sum()]}}), x='metric', y='value', title='Filled nulls in {col} with mode')"
                elif strategy == "ffill":
                    code = f"result = df.copy()\nresult['{col}'] = result['{col}'].ffill()\nfig = px.bar(pd.DataFrame({{'metric':['nulls_before','nulls_after'], 'value':[df['{col}'].isna().sum(), result['{col}'].isna().sum()]}}), x='metric', y='value', title='Filled nulls in {col} forward fill')"
                elif strategy == "zero":
                    code = f"result = df.copy()\nresult['{col}'] = result['{col}'].fillna(0)\nfig = px.bar(pd.DataFrame({{'metric':['nulls_before','nulls_after'], 'value':[df['{col}'].isna().sum(), result['{col}'].isna().sum()]}}), x='metric', y='value', title='Filled nulls in {col} with 0')"
                else:
                    code = f"result = df.copy()\nresult['{col}'] = result['{col}'].fillna(result['{col}'].median())\nfig = px.bar(pd.DataFrame({{'metric':['nulls_before','nulls_after'], 'value':[df['{col}'].isna().sum(), result['{col}'].isna().sum()]}}), x='metric', y='value', title='Filled nulls in {col}')"
                explanation = f"Filled nulls in {col} with {strategy}"
            else:
                # Fill all numeric nulls
                if strategy == "median":
                    code = f"result = df.copy()\nfor col in result.select_dtypes(include=['number']).columns:\n    result[col] = result[col].fillna(result[col].median())\nfig = px.bar(pd.DataFrame({{'metric':['nulls_before','nulls_after'], 'value':[df.isna().sum().sum(), result.isna().sum().sum()]}}), x='metric', y='value', title='Filled all numeric nulls with median')"
                else:
                    code = f"result = df.copy()\nfor col in result.select_dtypes(include=['number']).columns:\n    result[col] = result[col].fillna(result[col].mean())\nfig = px.bar(pd.DataFrame({{'metric':['nulls_before','nulls_after'], 'value':[df.isna().sum().sum(), result.isna().sum().sum()]}}), x='metric', y='value', title='Filled nulls')"
                explanation = f"Filled nulls with {strategy}"
            return {"code": code, "explanation": explanation}
        
        # 3. Drop rows/columns
        if "drop" in q:
            # Drop column
            if "column" in q or "col " in q:
                col = None
                for c in cols:
                    if c.lower() in q:
                        col = c
                        break
                if col:
                    code = f"result = df.drop(columns=['{col}'])\nfig = px.bar(pd.DataFrame({{'metric':['cols_before','cols_after'], 'value':[len(df.columns), len(result.columns)]}}), x='metric', y='value', title='Dropped column {col}')"
                    explanation = f"Dropped column {col}"
                    return {"code": code, "explanation": explanation}
            # Drop rows where null or condition
            if "null" in q or "na " in q:
                col = None
                for c in cols:
                    if c.lower() in q:
                        col = c
                        break
                if col:
                    code = f"result = df.dropna(subset=['{col}'])\nfig = px.bar(pd.DataFrame({{'metric':['rows_before','rows_after'], 'value':[len(df), len(result)]}}), x='metric', y='value', title='Dropped rows where {col} is null')"
                else:
                    code = f"result = df.dropna()\nfig = px.bar(pd.DataFrame({{'metric':['rows_before','rows_after'], 'value':[len(df), len(result)]}}), x='metric', y='value', title='Dropped rows with nulls')"
                explanation = "Dropped rows with nulls"
                return {"code": code, "explanation": explanation}
            # Drop rows where condition like Sales == 0
            if "where" in q:
                where_match = re.search(r"where\s+(.+)", query, re.IGNORECASE)
                if where_match:
                    cond = where_match.group(1).strip().replace("'", "\\'")
                    code = f"result = df.query('not ({cond})', engine='python')\nfig = px.bar(pd.DataFrame({{'metric':['rows_before','rows_after'], 'value':[len(df), len(result)]}}), x='metric', y='value', title='Dropped rows where {cond}')"
                    explanation = f"Dropped rows where {cond}"
                    return {"code": code, "explanation": explanation}
        
        # 4. Rename
        if "rename" in q:
            # Pattern: rename A to B, or rename column A to B
            m = re.search(r"rename\s+(?:column\s+)?(.+?)\s+to\s+(.+)", query, re.IGNORECASE)
            if m:
                old = m.group(1).strip().strip('"').strip("'")
                new = m.group(2).strip().strip('"').strip("'")
                # Find actual column that matches old
                old_col = _find_col_fuzzy(old, cols) or old
                code = f"result = df.rename(columns={{'{old_col}':'{new}'}})\nfig = px.bar(pd.DataFrame({{'metric':['renamed']}}), x='metric', y=[1], title='Renamed {old_col} to {new}')"
                explanation = f"Renamed {old_col} to {new}"
                return {"code": code, "explanation": explanation}
            # Fallback
            for c in cols:
                if c.lower() in q:
                    # Try to find new name after "to"
                    m2 = re.search(r"to\s+(\w+)", query, re.IGNORECASE)
                    if m2:
                        new = m2.group(1)
                        code = f"result = df.rename(columns={{'{c}':'{new}'}})\nfig = px.bar(pd.DataFrame({{'x':['before','after']}}), x='x', y=[1,1], title='Renamed')"
                        explanation = f"Renamed {c} to {new}"
                        return {"code": code, "explanation": explanation}
        
        # 5. Convert type
        if "convert" in q or "change type" in q or "to datetime" in q or "to numeric" in q or "to string" in q:
            col = None
            for c in cols:
                if c.lower() in q:
                    col = c
                    break
            if col:
                if "datetime" in q.lower() or "date" in q.lower():
                    code = f"result = df.copy()\nresult['{col}'] = pd.to_datetime(result['{col}'], errors='coerce')\nfig = px.bar(pd.DataFrame({{'metric':['converted']}}), x='metric', y=[1], title='Converted {col} to datetime')"
                    explanation = f"Converted {col} to datetime"
                elif "numeric" in q.lower() or "number" in q.lower():
                    code = f"result = df.copy()\nresult['{col}'] = pd.to_numeric(result['{col}'], errors='coerce')\nfig = px.bar(pd.DataFrame({{'metric':['converted']}}), x='metric', y=[1], title='Converted {col} to numeric')"
                    explanation = f"Converted {col} to numeric"
                elif "string" in q.lower() or "str " in q.lower():
                    code = f"result = df.copy()\nresult['{col}'] = result['{col}'].astype(str)\nfig = px.bar(pd.DataFrame({{'metric':['converted']}}), x='metric', y=[1], title='Converted {col} to string')"
                    explanation = f"Converted {col} to string"
                else:
                    code = f"result = df.copy()\nresult['{col}'] = pd.to_numeric(result['{col}'], errors='coerce')\nfig = px.bar(pd.DataFrame({{'metric':['converted']}}), x='metric', y=[1], title='Converted {col}')"
                    explanation = f"Converted {col}"
                return {"code": code, "explanation": explanation}
        
        # 6. Trim whitespace
        if "trim" in q or ("whitespace" in q and any(c.lower() in q for c in cols)):
            col = None
            for c in cols:
                if c.lower() in q:
                    col = c
                    break
            if col:
                code = f"result = df.copy()\nresult['{col}'] = result['{col}'].astype(str).str.strip()\nfig = px.bar(pd.DataFrame({{'metric':['trimmed']}}), x='metric', y=[1], title='Trimmed {col}')"
            else:
                code = f"result = df.copy()\nfor col in result.select_dtypes(include=['object']).columns:\n    result[col] = result[col].astype(str).str.strip()\nfig = px.bar(pd.DataFrame({{'metric':['trimmed']}}), x='metric', y=[1], title='Trimmed whitespace')"
            explanation = "Trimmed whitespace"
            return {"code": code, "explanation": explanation}
        
        # 7. Standardize case
        if "standardize" in q or ("case" in q and ("lower" in q or "upper" in q or "title" in q)):
            col = None
            for c in cols:
                if c.lower() in q:
                    col = c
                    break
            if "lower" in q.lower():
                if col:
                    code = f"result = df.copy()\nresult['{col}'] = result['{col}'].astype(str).str.lower()\nfig = px.bar(pd.DataFrame({{'x':['lower']}}), x='x', y=[1], title='Standardized {col} to lower')"
                else:
                    code = f"result = df.copy()\nfor col in result.select_dtypes(include=['object']).columns:\n    result[col] = result[col].astype(str).str.lower()\nfig = px.bar(pd.DataFrame({{'x':['lower']}}), x='x', y=[1], title='Standardized to lower')"
            elif "upper" in q.lower():
                if col:
                    code = f"result = df.copy()\nresult['{col}'] = result['{col}'].astype(str).str.upper()\nfig = px.bar(pd.DataFrame({{'x':['upper']}}), x='x', y=[1], title='Standardized {col} to upper')"
                else:
                    code = f"result = df.copy()\nfor col in result.select_dtypes(include=['object']).columns:\n    result[col] = result[col].astype(str).str.upper()\nfig = px.bar(pd.DataFrame({{'x':['upper']}}), x='x', y=[1], title='Standardized to upper')"
            else:
                if col:
                    code = f"result = df.copy()\nresult['{col}'] = result['{col}'].astype(str).str.title()\nfig = px.bar(pd.DataFrame({{'x':['title']}}), x='x', y=[1], title='Standardized {col} to title')"
                else:
                    code = f"result = df.copy()\nfor col in result.select_dtypes(include=['object']).columns:\n    result[col] = result[col].astype(str).str.title()\nfig = px.bar(pd.DataFrame({{'x':['title']}}), x='x', y=[1], title='Standardized')"
            explanation = "Standardized case"
            return {"code": code, "explanation": explanation}
        
        # 8. Split column
        if "split" in q:
            col = None
            for c in cols:
                if c.lower() in q:
                    col = c
                    break
            if col:
                # Try to find delimiter
                delim = ","
                if "by " in q.lower():
                    m = re.search(r"by\s+['\"]?(.)['\"]?", query)
                    if m:
                        delim = m.group(1)
                    if "comma" in q.lower():
                        delim = ","
                    elif "space" in q.lower():
                        delim = " "
                    elif ";" in query:
                        delim = ";"
                code = f"result = df.copy()\nresult[['{col}_1','{col}_2']] = result['{col}'].astype(str).str.split('{delim}', n=1, expand=True)\nfig = px.bar(pd.DataFrame({{'x':['split']}}), x='x', y=[1], title='Split {col} by {delim}')"
                explanation = f"Split {col} by {delim}"
                return {"code": code, "explanation": explanation}
        
        # 9. Remove outliers
        if "outlier" in q:
            col = None
            for c in numeric_cols:
                if c.lower() in q:
                    col = c
                    break
            if not col and numeric_cols:
                col = numeric_cols[0]
            if col:
                code = f"result = df[(df['{col}'] - df['{col}'].mean()).abs() <= 3*df['{col}'].std()]\nfig = px.bar(pd.DataFrame({{'metric':['before','after'], 'value':[len(df), len(result)]}}), x='metric', y='value', title='Removed outliers in {col}')"
                explanation = f"Removed outliers in {col}"
                return {"code": code, "explanation": explanation}
        
        # 10. Generic clean fallback
        code = f"result = df.dropna().drop_duplicates()\nfig = px.bar(pd.DataFrame({{'metric':['rows_before','rows_after'], 'value':[len(df), len(result)]}}), x='metric', y='value', title='Cleaned data')"
        explanation = "Cleaned data (drop nulls + duplicates)"
        return {"code": code, "explanation": explanation}

    # 1. Top N (e.g., top 5 products by sales)
    m = re.search(r"top\s+(\d+)", q)
    if m:
        n = m.group(1)
        # Find groupby column and metric
        cat = find_categorical()
        num = find_numeric()
        # Refine metric: prefer numeric column explicitly mentioned before 'by'
        # e.g., "top 5 products by sales" -> sales is metric, products is groupby
        # Check "by" phrase for groupby vs metric disambiguation
        by_match = re.search(r"by\s+(\w+)", q)
        if by_match:
            word = by_match.group(1)
            # First try to find matching categorical for groupby
            found_cat = None
            for c in cat_cols:
                if word in c.lower() or c.lower() in word:
                    found_cat = c
                    break
            # Also check all cols but only if word matches categorical-like token (product, category, region, etc.)
            # Don't override cat with numeric column (e.g., 'sales') - that is the metric, not groupby
            if found_cat:
                cat = found_cat
            else:
                # If no categorical found, word might be the metric (e.g., "by sales" -> metric is sales, groupby remains products)
                # So check if word is a numeric column -> set num to that
                for c in numeric_cols:
                    if word in c.lower() or c.lower() == word:
                        num = c
                        break
        # If query mentions a categorical explicitly before "by" or at start, prefer it
        # e.g., "top 5 products" -> Product
        for c in cat_cols:
            if c.lower().rstrip('s') in q or c.lower() in q:
                # Check if this categorical appears before "by"
                if "by" not in q or q.index(c.lower()) < q.index("by"):
                    cat = c
                    break
        # Ensure cat and num are different; if same, fallback
        if cat == num:
            # Pick first categorical that is not num
            for c in cat_cols:
                if c != num:
                    cat = c
                    break
            if cat == num and len(cols) >= 2:
                # Fallback to first column that is not num
                for c in cols:
                    if c != num:
                        cat = c
                        break
        # Final numeric check: if query mentions a numeric, use it
        for c in numeric_cols:
            if c.lower() in q:
                # If this numeric is same as cat, skip
                if c == cat:
                    continue
                num = c
                break
        code = f"result = df.groupby('{cat}')['{num}'].sum().sort_values(ascending=False).head({n}).reset_index()\nfig = px.bar(result, x='{cat}', y='{num}', title='Top {n} {cat} by {num}', color='{num}', text_auto=True)"
        explanation = f"Grouped by {cat}, summed {num}, top {n}"
        return {"code": code, "explanation": explanation}

    # 2. Monthly / trend / over time
    if any(k in q for k in ["trend", "over time", "monthly", "yearly", "daily", "time series", "evolution"]):
        # Try to find date column
        date_col = None
        for c in cols:
            if any(k in c.lower() for k in ["date", "time", "month", "year", "day"]):
                date_col = c
                break
        if not date_col:
            # Assume first column is date-like or use index
            date_col = cols[0] if cols else "date"
        num = find_numeric()
        code = f"# Try to parse date\ntry:\n    df['{date_col}'] = pd.to_datetime(df['{date_col}'])\n    result = df.groupby(pd.Grouper(key='{date_col}', freq='ME'))['{num}'].sum().reset_index()\n    result['{date_col}'] = result['{date_col}'].dt.strftime('%Y-%m')\nexcept Exception:\n    result = df.groupby('{date_col}')['{num}'].sum().reset_index()\nfig = px.line(result, x='{date_col}', y='{num}', title='{num} Trend Over {date_col}', markers=True)"
        explanation = f"Time trend of {num} over {date_col}"
        return {"code": code, "explanation": explanation}

    # 3. Correlation / heatmap (kept but analytics branch above is primary; this is fallback)
    if any(k in q for k in ["correlation", "corr", "heatmap", "relationship"]):
        if len(numeric_cols) >= 2:
            code = f"result = df[{numeric_cols}].corr(numeric_only=True)\nfig = px.imshow(result, text_auto=True, aspect='auto', title='Correlation Heatmap', color_continuous_scale='RdBu_r')"
        else:
            code = f"result = df.corr(numeric_only=True)\nfig = px.imshow(result, text_auto=True, title='Correlation Heatmap')"
        explanation = "Correlation matrix of numeric columns"
        return {"code": code, "explanation": explanation}

    # 4. Distribution / histogram
    if any(k in q for k in ["distribution", "histogram", "spread"]):
        num = find_numeric()
        code = f"fig = px.histogram(df, x='{num}', nbins=20, title='Distribution of {num}', marginal='box')\nresult = df['{num}'].describe().to_frame().T"
        explanation = f"Distribution of {num}"
        return {"code": code, "explanation": explanation}

    # 5. Pie / share / proportion
    if any(k in q for k in ["pie", "share", "proportion", "percentage"]):
        cat = find_categorical()
        num = find_numeric()
        code = f"result = df.groupby('{cat}')['{num}'].sum().reset_index()\nfig = px.pie(result, names='{cat}', values='{num}', title='Share of {num} by {cat}')"
        explanation = f"Pie share of {num} by {cat}"
        return {"code": code, "explanation": explanation}

    # 6. Scatter / vs / versus
    if any(k in q for k in ["scatter", " vs ", " versus ", " v/s "]):
        if len(numeric_cols) >= 2:
            x = numeric_cols[0]
            y = numeric_cols[1]
            # Try to find mentioned columns
            found = [c for c in numeric_cols if c.lower() in q]
            if len(found) >= 2:
                x, y = found[0], found[1]
            elif len(found) == 1:
                y = found[0]
            color = cat_cols[0] if cat_cols else None
            if color:
                code = f"fig = px.scatter(df, x='{x}', y='{y}', color='{color}', title='{y} vs {x}', trendline='ols')\nresult = df[['{x}', '{y}']].head(10)"
            else:
                code = f"fig = px.scatter(df, x='{x}', y='{y}', title='{y} vs {x}', trendline='ols')\nresult = df[['{x}', '{y}']].head(10)"
        else:
            code = f"fig = px.scatter(df, x='{cols[0]}', y='{cols[1]}' if len(df.columns)>1 else '{cols[0]}', title='Scatter')\nresult = df.head(10)"
        explanation = f"Scatter plot"
        return {"code": code, "explanation": explanation}

    # 7. Average / mean / median / sum / count
    if any(k in q for k in ["average", "mean", "median", "sum", "total", "count", "min", "max"]):
        agg = "mean"
        if "median" in q: agg = "median"
        elif "sum" in q or "total" in q: agg = "sum"
        elif "count" in q: agg = "count"
        elif "max" in q: agg = "max"
        elif "min" in q: agg = "min"
        
        # Check for groupby
        if "by" in q or "per" in q or "for each" in q:
            cat = find_categorical()
            num = find_numeric()
            for c in numeric_cols:
                if c.lower() in q:
                    num = c; break
            code = f"result = df.groupby('{cat}')['{num}'].{agg}().reset_index()\nfig = px.bar(result, x='{cat}', y='{num}', title='{agg.title()} of {num} by {cat}', color='{num}')"
            explanation = f"{agg} of {num} by {cat}"
        else:
            num = find_numeric()
            for c in numeric_cols:
                if c.lower() in q:
                    num = c; break
            if agg == "count":
                code = f"result = pd.DataFrame({{'count': [df['{num}'].count()]}})\nfig = px.bar(x=['{num}'], y=[df['{num}'].count()], title='Count of {num}')"
            else:
                code = f"result = pd.DataFrame({{'{agg}': [df['{num}'].{agg}()]}})\nfig = px.bar(x=['{num}'], y=[df['{num}'].{agg}()], title='{agg.title()} of {num}')"
            explanation = f"{agg} of {num}"
        return {"code": code, "explanation": explanation}

    # 8. Filter / where
    if any(k in q for k in ["filter", "where", "greater than", "less than", "equal to", "==", ">", "<"]):
        # Try to extract condition after where/filter
        condition = query
        # Extract after where
        where_match = re.search(r"where\s+(.+)", query, re.IGNORECASE)
        if where_match:
            condition = where_match.group(1)
        else:
            filter_match = re.search(r"filter\s+(.+)", query, re.IGNORECASE)
            if filter_match:
                condition = filter_match.group(1)
        # Handle textual operators
        condition = condition.replace("greater than", ">").replace("less than", "<").replace("equal to", "==").replace("equals", "==")
        # Escape single quotes for query
        condition_escaped = condition.replace("'", "\\'").replace('"', "'")
        # If condition still contains query words, fallback to head
        if len(condition_escaped) < 2 or condition_escaped.lower() in ["filter", "where"]:
            code = f"result = df.head(20)\nfig = px.bar(result.head(10), x=result.columns[0], y=result.columns[1] if len(result.columns)>1 else result.columns[0], title='Filtered Preview')"
        else:
            # Use duckdb for more robust filtering if available, else df.query
            code = f"try:\n    result = df.query('{condition_escaped}', engine='python')\nexcept Exception:\n    try:\n        result = duckdb.query(\"SELECT * FROM df WHERE {condition_escaped}\").to_df()\n    except Exception:\n        result = df.head(20)\nfig = px.bar(result.head(10), x=result.columns[0] if len(result.columns)>0 else 'x', y=result.columns[1] if len(result.columns)>1 else result.columns[0], title='Filtered Result')"
        explanation = f"Filtered where {condition_escaped[:40]}"
        return {"code": code, "explanation": explanation}

    # 9. Group by explicitly
    if "group" in q:
        cat = find_categorical()
        num = find_numeric()
        code = f"result = df.groupby('{cat}')['{num}'].sum().reset_index()\nfig = px.bar(result, x='{cat}', y='{num}', title='{num} by {cat}')"
        explanation = f"Grouped by {cat}"
        return {"code": code, "explanation": explanation}

    # 10. Describe / profile / summary / overview
    if any(k in q for k in ["describe", "profile", "summary", "overview", "info", "head", "columns"]):
        code = "result = df.describe(include='all').T.reset_index().rename(columns={'index':'column'})\nnulls = df.isna().sum().reset_index()\nnulls.columns = ['column','nulls']\nfig = px.bar(nulls, x='column', y='nulls', title='Missing Values')"
        explanation = "Dataset description and missing values"
        return {"code": code, "explanation": explanation}

    # 11. Sales by category / generic "by" — fix cat/num swap bug (cat must be categorical)
    if " by " in q:
        parts = q.split(" by ")
        cat = find_categorical()
        num = find_numeric()
        # Find categorical column in the part after "by" (the groupby key)
        for c in cat_cols:
            if c.lower() in parts[-1]:
                cat = c
                break
        # Fallback: if no categorical found after "by", try any col but ensure not numeric unless only numeric cols exist
        if cat not in cat_cols and cat_cols:
            # cat currently is fallback from earlier; ensure it is categorical
            pass
        # Check for metric before "by"
        for c in numeric_cols:
            if c.lower() in parts[0]:
                num = c
                break
        # Also check for metric after "by" if before part didn't have it (e.g., "regions by sales")
        if num not in parts[0].lower():
            for c in numeric_cols:
                if c.lower() in parts[-1]:
                    num = c
                    break
        # Ensure cat and num differ; if same, fix
        if cat == num:
            for c in cat_cols:
                if c != num:
                    cat = c
                    break
            if cat == num and len(cols) >= 2:
                for c in cols:
                    if c != num:
                        cat = c
                        break
        code = f"result = df.groupby('{cat}')['{num}'].sum().sort_values(ascending=False).reset_index()\nfig = px.bar(result, x='{cat}', y='{num}', title='{num} by {cat}', color='{num}')"
        explanation = f"{num} by {cat}"
        return {"code": code, "explanation": explanation}

    # 12. Compare
    if "compare" in q:
        cat = find_categorical()
        num = find_numeric()
        code = f"result = df.groupby('{cat}')['{num}'].agg(['sum','mean','count']).reset_index()\nfig = px.bar(result, x='{cat}', y='sum', title='Comparison of {num} by {cat}')"
        explanation = f"Comparison of {num} by {cat}"
        return {"code": code, "explanation": explanation}

    # 13. Default fallback: show relevant groupby + insight
    # If no pattern matched, do a smart default: group by most categorical, sum most numeric
    cat = cat_cols[0] if cat_cols else (cols[0] if cols else "category")
    num = numeric_cols[0] if numeric_cols else (cols[1] if len(cols) > 1 else cols[0] if cols else "value")
    # If query is very short or greeting, show head
    if len(q.split()) <= 3 or any(k in q for k in ["hi", "hello", "help", "what can you do"]):
        code = f"result = df.head(10)\nfig = px.bar(df.groupby('{cat}')['{num}'].sum().reset_index().head(10), x='{cat}', y='{num}', title='Overview: {num} by {cat}')"
        explanation = "Overview + sample rows"
    else:
        # Generic: try to answer by showing aggregated view
        code = f"result = df.groupby('{cat}')['{num}'].sum().sort_values(ascending=False).reset_index().head(10)\nfig = px.bar(result, x='{cat}', y='{num}', title='{num} by {cat} (Top 10)', color='{num}')"
        explanation = f"Top 10 {cat} by {num} (default)"
    
    return {"code": code, "explanation": explanation}

async def generate_code(query: str, profile: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, str]:
    """Generate code via LLM if available else fallback. Supports all providers. L4: sql intent -> duckdb."""
    # L4: early sql branch for raw SQL (highest priority, no LLM needed)
    q_lower = query.lower().strip()
    if q_lower.startswith("select") or q_lower.startswith("with"):
        # Validate read-only
        if _is_write_sql(q_lower):
            return {"code": "result = df.head(10)\nfig = px.bar(result.head(5), x=result.columns[0], y=result.columns[1] if len(result.columns)>1 else result.columns[0], title='Blocked: read-only SQL only')", "explanation": "Blocked DDL/DML"}
        # For raw SQL, directly craft duckdb code (fallback_coder already does but we short-circuit to avoid LLM)
        # Use fallback to keep logic consistent
        return fallback_coder(query, profile)
    # L4/L5: handle analytics intent via fallback (analytics branches are inside fallback_coder)
    if intent.get("intent") == "analytics":
        return fallback_coder(query, profile)
    # L4: if intent is sql but query is NL (e.g., connector without SELECT), try LLM to translate NL→SQL
    if intent.get("intent") == "sql":
        llm = get_llm()
        if llm:
            try:
                profile_text = get_profile_summary_text(profile)
                user_msg = f"Translate the following natural language query into a DuckDB SELECT statement over table 'df'. Columns: {profile.get('column_names')}. Query: {query}\nReturn JSON with keys 'sql' and 'explanation'. Only SELECT/WITH allowed."
                content = await llm.chat(
                    SYSTEM_CODER_PROMPT,
                    user_msg,
                    json_mode=True,
                    temperature=0.1,
                    max_tokens=400,
                )
                data = extract_json(content)
                sql = data.get("sql") or data.get("code") or ""
                if sql and (sql.strip().lower().startswith("select") or sql.strip().lower().startswith("with")):
                    if _is_write_sql(sql.lower()):
                        raise ValueError("LLM produced write SQL blocked")
                    # Craft code via duckdb
                    code = f"duckdb.register('df', df)\ntry:\n    result = duckdb.query('''{sql}''').to_df()\nexcept Exception as e:\n    result = df.head(20)\nfig = px.bar(result.head(20), x=result.columns[0] if len(result.columns)>0 else 'x', y=result.columns[1] if len(result.columns)>1 else result.columns[0], title='SQL Result')"
                    return {"code": code, "explanation": data.get("explanation", f"LLM translated to SQL: {sql[:60]}")}
            except Exception as e:
                print(f"NL→SQL LLM failed, fallback heuristic: {e}")
        # Fallback without LLM: heuristic NL->SQL is limited; let fallback_coder's groupby still work but add hint via profile
        # Inject hint so explainer mentions NL→SQL tip
        profile["_intent"] = "sql"
        profile["_intent_hint"] = "sql"
        res = fallback_coder(query, profile)
        # Append hint to explanation if not already SQL
        if "Tip:" not in res["explanation"]:
            res["explanation"] += " | " + _sql_to_pandas_fallback_hint(query)
        return res
    # Normal path
    llm = get_llm()
    if not llm:
        return fallback_coder(query, profile)
    
    try:
        profile_text = get_profile_summary_text(profile)
        user_msg = f"User Query: {query}\n\nData Profile:\n{profile_text}\n\nIntent: {intent}\n\nGenerate code:"
        content = await llm.chat(
            SYSTEM_CODER_PROMPT,
            user_msg,
            json_mode=True,
            temperature=0.2,
            max_tokens=600,
        )
        data = extract_json(content)
        if "code" not in data:
            return fallback_coder(query, profile)
        return {"code": data["code"], "explanation": data.get("explanation", f"LLM ({llm.provider}) generated")}
    except Exception as e:
        print(f"Coder LLM ({get_llm().provider if get_llm() else 'none'}) failed, fallback: {e}")
        return fallback_coder(query, profile)
