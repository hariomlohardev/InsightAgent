from typing import Dict, Any
from app.core import storage
from app.core.profiling import profile_dataframe
from app.agent import planner, coder, executor, explainer


async def process_query(dataset_id: str, query: str, conversation_id: str = None) -> Dict[str, Any]:
    """Full agent pipeline: plan -> code -> execute -> explain. Handles cleaning via wrangle diff."""
    # run blocking IO off event loop
    import asyncio

    df = await asyncio.to_thread(storage.load_dataset_df, dataset_id)
    # stable profiling cache key dataset_id:version
    try:
        _meta = storage.get_dataset_meta(dataset_id)
        _ver = _meta.get("current_version", 0) if _meta else 0
    except:
        _ver = 0
    profile = await asyncio.to_thread(profile_dataframe, df, 5, True, dataset_id, _ver)
    intent = await planner.plan(query, profile)
    # For cleaning intent, also compute diff via wrangle for richer response
    is_cleaning = intent.get("intent") == "cleaning"
    code_res = await coder.generate_code(query, profile, intent)
    code = code_res["code"]
    code_exp = code_res.get("explanation", "")
    exec_res = await asyncio.to_thread(executor.execute_code, code, df)
    diff = None
    if is_cleaning and exec_res.get("success"):
        try:
            from app.core.wrangle import diff_dataframes

            after_df = exec_res.get("_after_df")
            if isinstance(after_df, pd.DataFrame):
                diff = diff_dataframes(df, after_df)
        except Exception:
            diff = None

    # 4. Explain
    insight = await explainer.explain(
        query,
        exec_res.get("result_json"),
        exec_res.get("error"),
        profile,
        exec_res.get("stdout", ""),
    )

    # Save conversation
    # User message
    storage.save_conversation_message(dataset_id, conversation_id or "", "user", {"query": query})
    # Need to get conversation_id if new
    if not conversation_id:
        # Find latest conv for this dataset created just now: list and get first
        convs = storage.list_conversations(dataset_id)
        if convs:
            # The just created one should be latest
            conversation_id = convs[0]["id"]
        # But our save function generated new id internally, we need to capture it
        # Instead we should call save and capture return. Refactor: save returns id
        # Already did, but we passed "" so it generated. Need to redo correctly below
        pass

    # Actually handle conversation_id properly: if None, generate via save
    if not conversation_id:
        # The previous save generated an id but we didn't capture. Let's get it via listing.
        # Better: call save again with proper capture - but we already saved.
        # We'll fetch latest
        convs = storage.list_conversations(dataset_id)
        conversation_id = convs[0]["id"] if convs else "unknown"

    # Save assistant message
    # Ensure conversation_id exists
    assistant_content = {
        "query": query,
        "intent": intent,
        "generated_code": code,
        "code_explanation": code_exp,
        "success": exec_res["success"],
        "result": exec_res.get("result_json"),
        "chart": exec_res.get("chart_json"),
        "insight": insight,
        "error": exec_res.get("error"),
        "stdout": exec_res.get("stdout"),
    }
    # Use existing conversation_id
    storage.save_conversation_message(dataset_id, conversation_id, "assistant", assistant_content)

    return {
        "conversation_id": conversation_id,
        "query": query,
        "intent": intent,
        "generated_code": code,
        "code_explanation": code_exp,
        "success": exec_res["success"],
        "result": exec_res.get("result_json"),
        "chart": exec_res.get("chart_json"),
        "insight": insight,
        "error": exec_res.get("error"),
        "stdout": exec_res.get("stdout"),
    }


# BF-03 chat cache <5ms HIT via chat:{id}:{qhash}:{version}
async def process_query_v2(
    dataset_id: str, query: str, conversation_id: str = None
) -> Dict[str, Any]:
    from app.core import storage as st
    import uuid, hashlib, time

    try:
        from app.core.cache import get as cache_get, set as cache_set, cache_key

        _cache_available = True
    except Exception:
        _cache_available = False
    # L4: if dataset is connector, force intent to sql even if query is NL (so coder can try NL→SQL)
    meta = st.get_dataset_meta(dataset_id)
    is_connector = meta and meta.get("type") == "connector"
    # BF-03 check cache before compute
    _version = meta.get("current_version", 0) if meta else 0
    _qhash = hashlib.sha256(query.strip().encode()).hexdigest()[:12] if _cache_available else ""
    _ck = cache_key(f"chat:{dataset_id}:{_qhash}:{_version}") if _cache_available else None
    if _cache_available and _ck:
        _cached = cache_get(_ck)
        if _cached and isinstance(_cached, dict) and _cached.get("query") == query:
            # bump hit marker for API layer
            _cached["_cache_hit"] = True
            return _cached
    import asyncio

    df = await asyncio.to_thread(st.load_dataset_df, dataset_id)
    profile = await asyncio.to_thread(profile_dataframe, df, 5, True, dataset_id, _version)
    if is_connector and not query.strip().lower().startswith(("select", "with")):
        # Inject hint so planner/coder treat as sql — preserve analytics intent
        ql = query.lower()
        if not any(
            k in ql
            for k in [
                "forecast",
                "predict",
                "outlier",
                "anomal",
                "segment",
                "cohort",
                "what if",
                "why",
                "explain",
                "correlation",
                "heatmap",
            ]
        ):
            profile["_intent_hint"] = "sql"
            profile["_intent"] = "sql"
    intent = await planner.plan(query, profile)
    # L4/L5: override intent for connectors so NL queries are treated as sql (enables NL→SQL) — but not for analytics
    if is_connector:
        if intent.get("intent") != "analytics" and not query.strip().lower().startswith(
            ("select", "with")
        ):
            # Don't hijack analytics queries like forecast/why/outlier on connectors — keep analytics intent
            is_analytics_q = any(
                k in query.lower()
                for k in [
                    "forecast",
                    "predict",
                    "outlier",
                    "segment",
                    "cohort",
                    "what if",
                    "why",
                    "explain",
                    "correlation",
                    "heatmap",
                ]
            )
            if not is_analytics_q:
                intent["intent"] = "sql"
                intent["chart_type"] = "bar"
                intent["_forced_connector"] = True
    code_res = await coder.generate_code(query, profile, intent)
    code = code_res["code"]
    code_exp = code_res.get("explanation", "")
    exec_res = await asyncio.to_thread(executor.execute_code, code, df)
    insight = await explainer.explain(
        query,
        exec_res.get("result_json"),
        exec_res.get("error"),
        profile,
        exec_res.get("stdout", ""),
    )

    # Conversation handling
    if not conversation_id:
        conversation_id = str(uuid.uuid4())[:8]
        # create conversation file directly
    # Save user
    st.save_conversation_message(dataset_id, conversation_id, "user", {"query": query})
    # Save assistant with diff for cleaning — single exec (exec_res._after_df)
    diff = None
    if intent.get("intent") == "cleaning" and exec_res.get("success"):
        try:
            from app.core.wrangle import diff_dataframes

            after_df = exec_res.get("_after_df")
            if isinstance(after_df, pd.DataFrame):
                diff = diff_dataframes(df, after_df)
            else:
                diff = {"before_shape": list(df.shape), "changed": True}
        except Exception:
            diff = None
    assistant_content = {
        "query": query,
        "intent": intent,
        "generated_code": code,
        "code_explanation": code_exp,
        "success": exec_res["success"],
        "result": exec_res.get("result_json"),
        "chart": exec_res.get("chart_json"),
        "insight": insight,
        "error": exec_res.get("error"),
        "stdout": exec_res.get("stdout"),
        "diff": diff,
    }
    st.save_conversation_message(dataset_id, conversation_id, "assistant", assistant_content)

    _result = {
        "conversation_id": conversation_id,
        "query": query,
        "intent": intent,
        "generated_code": code,
        "code_explanation": code_exp,
        "success": exec_res["success"],
        "result": exec_res.get("result_json"),
        "chart": exec_res.get("chart_json"),
        "insight": insight,
        "error": exec_res.get("error"),
        "stdout": exec_res.get("stdout"),
        "diff": diff,
    }
    # BF-03 set cache for next HIT <5ms
    if _cache_available and _ck:
        try:
            cache_set(_ck, _result, ttl=60)
        except Exception:
            pass
    return _result
