import os
import json
from typing import Dict, Any, Optional

from app.agent.prompts import SYSTEM_EXPLAINER_PROMPT

def fallback_explain(query: str, result_json: Optional[Dict[str, Any]], error: Optional[str], profile: Dict[str, Any]) -> str:
    """Template-based insights when no LLM."""
    if error:
        # Simplify error
        first_line = error.split("\n")[0][:200]
        return f"- ⚠️ Execution failed: {first_line}\n- Try rephrasing your query or check column names: {', '.join(profile.get('column_names', [])[:5])}"

    if not result_json:
        return "- No results to explain. Try a different query."

    rows = result_json.get("rows", 0)
    cols = result_json.get("columns", [])
    data = result_json.get("data", [])[:3]

    lines = []
    lines.append(f"- Query '{query}' returned **{rows} rows** with columns: {', '.join(cols[:5])}.")
    
    # Try to extract insight from data
    if data:
        # Assume first numeric column insight
        # Find numeric values in first row
        first = data[0]
        # Example: if result is grouped sum
        numeric_vals = []
        for k, v in first.items():
            try:
                fv = float(str(v).replace(",", ""))
                numeric_vals.append((k, fv, first))
            except:
                pass
        if numeric_vals:
            # Find max in data if grouped
            try:
                # Try to find column with max
                # Use first numeric col
                num_col = numeric_vals[0][0]
                # Find max row
                max_row = max(data, key=lambda r: float(str(r.get(num_col, 0)).replace(",", "")) if str(r.get(num_col, 0)).replace(".","",1).isdigit() else 0)
                cat_col = [k for k in max_row.keys() if k != num_col][0] if len(max_row) > 1 else "item"
                lines.append(f"- Highest **{num_col}** is **{max_row.get(num_col)}** for **{max_row.get(cat_col)}** (among top results).")
            except Exception:
                pass

    if rows > 1 and len(data) >= 2:
        lines.append(f"- Showing top {min(rows, len(data))} results out of {rows} total. Chart visualizes the distribution.")
    
    # Add tip
    lines.append(f"- Tip: Ask follow-ups like 'why trend?' or 'show correlation' for deeper insights.")

    return "\n".join(lines)

async def explain(query: str, result_json: Optional[Dict[str, Any]], error: Optional[str], profile: Dict[str, Any], stdout: str = "") -> str:
    """Use LLM if available else fallback."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return fallback_explain(query, result_json, error, profile)

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        
        # Build context
        result_summary = ""
        if result_json:
            result_summary = f"Result: {result_json.get('rows')} rows, columns {result_json.get('columns')}, sample data: {json.dumps(result_json.get('data', [])[:2], indent=2)}"
        if error:
            result_summary += f"\nError: {error[:500]}"
        if stdout:
            result_summary += f"\nStdout: {stdout[:500]}"

        profile_text = f"Dataset shape: {profile.get('shape')}, columns: {profile.get('column_names')}"

        user_msg = f"User Query: {query}\nProfile: {profile_text}\n{result_summary}\n\nProvide insights:"

        resp = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_EXPLAINER_PROMPT},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.3,
            max_tokens=400,
        )
        content = resp.choices[0].message.content
        return content.strip()
    except Exception as e:
        print(f"Explainer LLM failed: {e}")
        return fallback_explain(query, result_json, error, profile)
