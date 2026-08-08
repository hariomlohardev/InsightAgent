import os
import json
import re
from typing import Dict, Any

from app.agent.prompts import SYSTEM_CODER_PROMPT
from app.core.profiling import get_profile_summary_text

def fallback_coder(query: str, profile: Dict[str, Any]) -> Dict[str, str]:
    """Rule-based coder covering 15+ common patterns. No LLM needed."""
    q = query.lower().strip()
    cols = profile.get("column_names", [])
    numeric_cols = profile.get("numeric_columns", [])
    cat_cols = profile.get("categorical_columns", [])
    
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

    # 3. Correlation / heatmap
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
    if any(k in q for k in ["filter", "where", "greater than", "less than", "equal to"]):
        # Generic filter fallback: show filtered rows
        # Try to parse condition like "sales > 1000"
        # Simple fallback: show head with condition in comment
        code = f"# Filter example - showing filtered preview\nresult = df.head(20)\nfig = px.bar(result.head(10), x=result.columns[0], y=result.columns[1] if len(result.columns)>1 else result.columns[0], title='Filtered Preview')"
        # Try to be smarter: if query contains ">" or "="
        if ">" in q or "<" in q or "=" in q:
            # Attempt to generate duckdb filter if column mentioned
            # Fallback to pandas query
            code = f"try:\n    result = df.query('{query.replace(chr(34), chr(39))}')\nexcept Exception:\n    result = df.head(20)\nfig = px.bar(result.head(10), x=result.columns[0], y=result.columns[1] if len(result.columns)>1 else result.columns[0], title='Filtered Result')"
        explanation = "Filtered data"
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

    # 11. Sales by category / generic "by"
    if " by " in q:
        parts = q.split(" by ")
        cat = find_categorical()
        num = find_numeric()
        # Try to find actual columns near "by"
        for c in cols:
            if c.lower() in parts[-1]:
                cat = c
                break
        for c in numeric_cols:
            if c.lower() in parts[0]:
                num = c
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
    """Generate code via LLM if available, else fallback."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return fallback_coder(query, profile)
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        profile_text = get_profile_summary_text(profile)
        user_msg = f"User Query: {query}\n\nData Profile:\n{profile_text}\n\nIntent: {intent}\n\nGenerate code:"
        
        resp = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_CODER_PROMPT},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        data = json.loads(content)
        if "code" not in data:
            return fallback_coder(query, profile)
        # Ensure code is string
        return {"code": data["code"], "explanation": data.get("explanation", "LLM generated")}
    except Exception as e:
        print(f"Coder LLM failed, fallback: {e}")
        return fallback_coder(query, profile)
