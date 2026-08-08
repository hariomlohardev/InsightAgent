import re
from typing import Dict, Any, List
import os

from app.agent.prompts import SYSTEM_PLANNER_PROMPT

# Heuristic keywords
VISUAL_KEYWORDS = ["chart", "plot", "graph", "visual", "show", "display", "bar", "line", "pie", "scatter", "histogram", "heatmap", "trend"]
AGG_KEYWORDS = ["sum", "total", "average", "mean", "median", "count", "max", "min", "group by", "groupby", "aggregate"]
FILTER_KEYWORDS = ["top", "filter", "where", "sort", "highest", "lowest", "greater", "less"]
PROFILE_KEYWORDS = ["describe", "info", "profile", "columns", "overview", "summary", "shape", "head", "sample"]
INSIGHT_KEYWORDS = ["why", "explain", "insight", "trend", "correlation", "relationship", "compare", "analysis"]
CLEANING_KEYWORDS = ["clean", "remove null", "duplicate", "fill", "drop"]

CHART_MAP = {
    "bar": ["bar", "category", "by category", "by product", "by region"],
    "line": ["line", "trend", "over time", "monthly", "daily", "yearly", "time series"],
    "pie": ["pie", "proportion", "share", "distribution by"],
    "scatter": ["scatter", "correlation", "relationship", "vs", "versus"],
    "histogram": ["histogram", "distribution", "spread"],
    "heatmap": ["heatmap", "correlation matrix", "corr"],
}

def heuristic_plan(query: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    q = query.lower()
    intent = "visualization"  # default
    if any(k in q for k in PROFILE_KEYWORDS):
        intent = "profiling"
    elif any(k in q for k in INSIGHT_KEYWORDS):
        intent = "insight"
    elif any(k in q for k in CLEANING_KEYWORDS):
        intent = "cleaning"
    elif any(k in q for k in FILTER_KEYWORDS):
        intent = "filter"
    elif any(k in q for k in AGG_KEYWORDS):
        intent = "aggregation"
    elif any(k in q for k in VISUAL_KEYWORDS):
        intent = "visualization"
    # SQL detection
    if q.strip().startswith("select") or " from " in q and "select" in q:
        intent = "sql"

    chart_type = "none"
    for ct, keywords in CHART_MAP.items():
        if any(k in q for k in keywords):
            chart_type = ct
            break
    # Fallback: if intent is visualization and no chart detected, infer from data
    if intent == "visualization" and chart_type == "none":
        # If categorical + numeric -> bar, if time-like -> line
        if len(profile.get("categorical_columns", [])) > 0 and len(profile.get("numeric_columns", [])) > 0:
            chart_type = "bar"
        elif len(profile.get("numeric_columns", [])) >= 2:
            chart_type = "scatter"

    # Extract columns mentioned
    mentioned = []
    for col in profile.get("column_names", []):
        if col.lower() in q or col.lower().replace("_", " ") in q:
            mentioned.append(col)
        # Also fuzzy: if column without spaces appears
        # e.g., "sales" matches "Sales Amount"
        # Simple: check token overlap
    # Aggregation
    agg = ""
    for a in ["sum", "mean", "average", "count", "max", "min", "median"]:
        if a in q:
            agg = a
            break

    return {
        "intent": intent,
        "chart_type": chart_type,
        "columns": mentioned,
        "aggregation": agg,
    }

async def plan(query: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """Return intent plan. Use LLM if available else heuristic."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return heuristic_plan(query, profile)
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_PLANNER_PROMPT},
                {"role": "user", "content": f"Query: {query}\nColumns: {profile.get('column_names')}"}
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        import json
        content = resp.choices[0].message.content
        data = json.loads(content)
        # Validate
        if "intent" not in data:
            return heuristic_plan(query, profile)
        return data
    except Exception as e:
        print(f"Planner LLM failed, fallback heuristic: {e}")
        return heuristic_plan(query, profile)
