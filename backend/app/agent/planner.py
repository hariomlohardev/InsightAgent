import re
from typing import Dict, Any, List
import os

from app.agent.prompts import SYSTEM_PLANNER_PROMPT
from app.core.llm import get_llm, extract_json

# Heuristic keywords — L5 adds analytics
VISUAL_KEYWORDS = ["chart", "plot", "graph", "visual", "show", "display", "bar", "line", "pie", "scatter", "histogram", "heatmap", "trend"]
AGG_KEYWORDS = ["sum", "total", "average", "mean", "median", "count", "max", "min", "group by", "groupby", "aggregate"]
FILTER_KEYWORDS = ["top", "filter", "where", "sort", "highest", "lowest", "greater", "less"]
PROFILE_KEYWORDS = ["describe", "info", "profile", "columns", "overview", "summary", "shape", "head", "sample"]
INSIGHT_KEYWORDS = ["why", "explain", "insight", "trend", "relationship", "compare", "analysis"]
CLEANING_KEYWORDS = ["clean", "remove null", "duplicate", "fill", "drop", "rename", "convert", "trim", "standardize", "split", "merge", "pivot", "melt"]
ANALYTICS_KEYWORDS = ["forecast", "predict", "next", "outlier", "anomal", "segment", "cohort", "breakdown", "what if", "what-if", "whatif", "correlation", "heatmap", "why", "reason", "drop", "increase"]
# Note: "outlier" moved from cleaning to analytics — planner prioritizes analytics before cleaning

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
    # Analytics has priority for specific L5 intents (why/forecast/outlier/segment/what-if)
    # Check analytics before other fallbacks but after SQL
    # SQL detection — highest priority
    if q.strip().startswith("select") or q.strip().startswith("with") or (" from " in q and "select" in q):
        intent = "sql"
    elif any(k in q for k in ANALYTICS_KEYWORDS):
        # Distinguish correlation -> still visualization but we mark analytics for coder
        # Forecast/what-if/outlier/segment/why all go to analytics
        if any(x in q for x in ["forecast","predict","next"]):
            intent = "analytics"
        elif any(x in q for x in ["outlier","anomal"]):
            intent = "analytics"
        elif any(x in q for x in ["segment","cohort","breakdown"]):
            intent = "analytics"
        elif any(x in q for x in ["what if","what-if","whatif"]):
            intent = "analytics"
        elif any(x in q for x in ["why","explain","reason","drop","increase"]):
            # Only treat as analytics if question-like
            if "?" in q or any(w in q for w in ["why","explain","reason"]):
                intent = "analytics"
            elif any(w in q for w in ["drop","fall","decrease","increase"]):
                intent = "analytics"
            else:
                intent = "insight"
        elif "correlation" in q or "heatmap" in q:
            intent = "analytics"
        else:
            intent = "analytics"
    elif any(k in q for k in PROFILE_KEYWORDS):
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
    """Return intent plan. Use LLM if available else heuristic. Supports all providers."""
    llm = get_llm()
    if not llm:
        return heuristic_plan(query, profile)
    
    try:
        content = await llm.chat(
            SYSTEM_PLANNER_PROMPT,
            f"Query: {query}\nColumns: {profile.get('column_names')}",
            json_mode=True,
            temperature=0.1,
            max_tokens=300,
        )
        data = extract_json(content)
        if "intent" not in data:
            return heuristic_plan(query, profile)
        return data
    except Exception as e:
        print(f"Planner LLM ({llm.provider if llm else 'none'}) failed, fallback heuristic: {e}")
        return heuristic_plan(query, profile)
