from typing import Dict, Any
from app.core import storage
from app.core.profiling import profile_dataframe
from app.agent import planner, coder, executor, explainer

async def process_query(dataset_id: str, query: str, conversation_id: str = None) -> Dict[str, Any]:
    """Full agent pipeline: plan -> code -> execute -> explain."""
    # Load df
    df = storage.load_dataset_df(dataset_id)
    # Profile for context
    profile = profile_dataframe(df)

    # 1. Plan
    intent = await planner.plan(query, profile)

    # 2. Generate code
    code_res = await coder.generate_code(query, profile, intent)
    code = code_res["code"]
    code_exp = code_res.get("explanation", "")

    # 3. Execute
    exec_res = executor.execute_code(code, df)

    # 4. Explain
    insight = await explainer.explain(
        query,
        exec_res.get("result_json"),
        exec_res.get("error"),
        profile,
        exec_res.get("stdout", "")
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

# Fix: better wrapper that handles conversation_id correctly
async def process_query_v2(dataset_id: str, query: str, conversation_id: str = None) -> Dict[str, Any]:
    from app.core import storage as st
    import uuid
    df = st.load_dataset_df(dataset_id)
    profile = profile_dataframe(df)
    intent = await planner.plan(query, profile)
    code_res = await coder.generate_code(query, profile, intent)
    code = code_res["code"]
    code_exp = code_res.get("explanation", "")
    exec_res = executor.execute_code(code, df)
    insight = await explainer.explain(query, exec_res.get("result_json"), exec_res.get("error"), profile, exec_res.get("stdout", ""))

    # Conversation handling
    if not conversation_id:
        conversation_id = str(uuid.uuid4())[:8]
        # create conversation file directly
    # Save user
    st.save_conversation_message(dataset_id, conversation_id, "user", {"query": query})
    # Save assistant
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
    st.save_conversation_message(dataset_id, conversation_id, "assistant", assistant_content)

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
