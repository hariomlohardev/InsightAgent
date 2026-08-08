import os
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
st.set_page_config(page_title="InsightAgent - AI Data Analyst", layout="wide", page_icon="📊")

# Custom CSS
st.markdown("""
<style>
    .main-header {font-size: 2.2rem; font-weight: 700; margin-bottom: 0.2rem;}
    .sub-header {color: #666; margin-bottom: 1.5rem;}
    .chat-user {background: #e8f0fe; padding: 12px; border-radius: 10px; margin: 8px 0;}
    .chat-assistant {background: #f8f9fa; border: 1px solid #e9ecef; padding: 14px; border-radius: 10px; margin: 8px 0;}
    .stButton>button {width: 100%;}
</style>
""", unsafe_allow_html=True)

def backend_health():
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=3)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        return None

def list_datasets():
    try:
        r = requests.get(f"{BACKEND_URL}/api/datasets", timeout=5)
        if r.status_code == 200:
            return r.json()
        return []
    except:
        return []

def upload_dataset(file):
    try:
        files = {"file": (file.name, file.getvalue(), file.type)}
        r = requests.post(f"{BACKEND_URL}/api/datasets/upload", files=files, timeout=30)
        return r
    except Exception as e:
        return None

def get_dataset_details(dataset_id):
    try:
        r = requests.get(f"{BACKEND_URL}/api/datasets/{dataset_id}", timeout=10)
        if r.status_code == 200:
            return r.json()
        return None
    except:
        return None

def chat_query(dataset_id, query, conv_id=None):
    try:
        payload = {"dataset_id": dataset_id, "query": query, "conversation_id": conv_id}
        r = requests.post(f"{BACKEND_URL}/api/chat", json=payload, timeout=60)
        return r
    except Exception as e:
        return None

# Header
st.markdown('<div class="main-header">📊 InsightAgent</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Chat with your CSV/Excel in plain English — Get charts & insights instantly. Open Source + Private.</div>', unsafe_allow_html=True)

health = backend_health()
if health:
    st.success(f"✅ Backend connected — v{health.get('version','0.1.0')} | OpenAI: {'✅' if requests.get(f'{BACKEND_URL}/').json().get('openai_configured') else '⚠️ Fallback mode (no key, still works)'}")
else:
    st.error(f"❌ Backend not reachable at {BACKEND_URL}. Run: `uvicorn app.main:app --reload` in backend/ or `docker-compose up`")
    st.stop()

# Sidebar
with st.sidebar:
    st.header("📁 Datasets")
    st.caption("Upload CSV, Excel, JSON (max 100MB)")
    uploaded = st.file_uploader("Upload", type=["csv", "xlsx", "xls", "json"], label_visibility="collapsed")
    if uploaded:
        if st.button("⬆️ Upload & Analyze", type="primary"):
            with st.spinner("Uploading & profiling..."):
                resp = upload_dataset(uploaded)
                if resp is not None and resp.status_code == 200:
                    st.success(f"Uploaded: {resp.json()['original_filename']}")
                    st.rerun()
                else:
                    err = resp.text if resp else "No response"
                    st.error(f"Upload failed: {err}")

    st.divider()
    datasets = list_datasets()
    if not datasets:
        st.info("No datasets yet. Upload one to start.")
        dataset_id = None
    else:
        options = {f"{d['original_filename']} ({d['rows']} rows)": d["id"] for d in datasets}
        selected = st.selectbox("Select dataset", list(options.keys()))
        dataset_id = options[selected]

        # Quick actions per dataset
        st.markdown("**Actions**")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗑️ Delete"):
                requests.delete(f"{BACKEND_URL}/api/datasets/{dataset_id}")
                st.success("Deleted")
                st.rerun()
        with col2:
            if st.button("🔄 Refresh"):
                st.rerun()

    st.divider()
    st.markdown("**Example queries**")
    examples = [
        "Show top 5 products by sales",
        "Monthly sales trend",
        "Correlation heatmap",
        "Distribution of price",
        "Average sales by category",
        "Describe dataset",
    ]
    for ex in examples:
        if st.button(ex, key=f"ex_{ex}"):
            st.session_state["pending_query"] = ex

    st.divider()
    st.caption("💡 Tip: Add `OPENAI_API_KEY` to .env for smarter insights. Without it, rule-based mode works for 15+ common queries.")
    st.caption("GitHub: MIT Open Source | Premium Cloud: $19/mo")

if not datasets:
    # Empty state
    st.info("👋 **Welcome!** Upload a CSV/Excel file from the sidebar to start chatting with your data.")
    st.markdown("""
    **Try with sample data:**
    ```bash
    # sample_data/sales.csv is included
    ```
    Or download any CSV (e.g., sales, expenses) and upload.
    """)
    # Show sample data preview if exists
    if os.path.exists("sample_data/sales.csv"):
        st.subheader("📄 Sample Data Preview: sales.csv")
        try:
            df_sample = pd.read_csv("sample_data/sales.csv")
            st.dataframe(df_sample.head(10), use_container_width=True)
            if st.button("Use Sample Data (Upload sales.csv)"):
                with open("sample_data/sales.csv", "rb") as f:
                    files = {"file": ("sales.csv", f.read(), "text/csv")}
                    r = requests.post(f"{BACKEND_URL}/api/datasets/upload", files=files)
                    if r.status_code == 200:
                        st.success("Sample uploaded!")
                        st.rerun()
                    else:
                        st.error(r.text)
        except Exception as e:
            st.error(str(e))
    st.stop()

# Main area - dataset details
details = get_dataset_details(dataset_id)
if not details:
    st.error("Failed to load dataset details")
    st.stop()

# Store in session
if "conversation_id" not in st.session_state:
    st.session_state["conversation_id"] = None
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "current_dataset" not in st.session_state or st.session_state["current_dataset"] != dataset_id:
    st.session_state["current_dataset"] = dataset_id
    st.session_state["conversation_id"] = None
    st.session_state["messages"] = []

# Dataset header
meta = details["dataset"]
profile = details["profile"]
preview = details["preview"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Rows", meta["rows"])
col2.metric("Columns", meta["columns"])
col3.metric("File", meta["original_filename"][:20])
col4.metric("Dataset ID", meta["id"])

tabs = st.tabs(["💬 Chat", "📋 Data Preview", "🔍 Profiling", "📊 Quick Stats"])

with tabs[1]:
    st.subheader("Data Preview (first 10 rows)")
    df_prev = pd.DataFrame(preview["data"])
    st.dataframe(df_prev, use_container_width=True)
    st.json(profile["null_summary"])

    # Download
    if st.button("⬇️ Download Preview as CSV"):
        st.download_button("Download CSV", df_prev.to_csv(index=False), file_name="preview.csv")

with tabs[2]:
    st.subheader("Column Profiling")
    for col in profile["columns"]:
        with st.expander(f"{col['name']} ({col['dtype']}) - nulls: {col['nulls']}, unique: {col['unique']}"):
            st.json(col)
    st.subheader("Full Describe")
    st.json(profile["describe"])

with tabs[3]:
    st.subheader("Quick Visual Insights")
    # Auto chart: distribution of first numeric
    numeric_cols = profile.get("numeric_columns", [])
    cat_cols = profile.get("categorical_columns", [])
    if numeric_cols:
        sel = st.selectbox("Select numeric column for quick histogram", numeric_cols)
        df_preview_full = pd.DataFrame(preview["data"])
        # For quick chart we need actual numeric data - approximate from preview
        try:
            fig = px.histogram(pd.DataFrame(preview["data"]), x=sel, title=f"Distribution of {sel} (sample)", marginal="box")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(str(e))
    if cat_cols and numeric_cols:
        st.markdown("**Auto Groupby**")
        cat_sel = st.selectbox("Category", cat_cols, key="cat2")
        num_sel = st.selectbox("Value", numeric_cols, key="num2")
        try:
            df_full = pd.DataFrame(preview["data"])
            # Try to aggregate sample
            # This is just preview, not full data, but for demo
            st.caption("Preview aggregation (sample data only)")
            grp = pd.DataFrame(preview["data"]).groupby(cat_sel)[num_sel].sum().reset_index() if cat_sel in df_full.columns and num_sel in df_full.columns else None
            if grp is not None:
                fig2 = px.bar(grp, x=cat_sel, y=num_sel, title=f"{num_sel} by {cat_sel}")
                st.plotly_chart(fig2, use_container_width=True)
        except Exception as e:
            st.error(str(e))

with tabs[0]:
    st.subheader(f"💬 Chat with {meta['original_filename']}")
    st.caption(f"Ask anything. Columns: {', '.join(profile['column_names'])}")

    # Display chat history
    for msg in st.session_state["messages"]:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-user"><b>🧑 You:</b> {msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-assistant"><b>🤖 Agent:</b> {msg["insight"]}</div>', unsafe_allow_html=True)
            # Show code expander
            with st.expander("🔍 View Generated Code & Details"):
                st.code(msg.get("code", ""), language="python")
                st.caption(msg.get("code_explanation", ""))
                if msg.get("error"):
                    st.error(msg["error"][:1000])
                if msg.get("stdout"):
                    st.text(msg["stdout"][:500])
            # Show table
            if msg.get("result"):
                res = msg["result"]
                try:
                    df_res = pd.DataFrame(res["data"])
                    st.dataframe(df_res, use_container_width=True)
                    st.caption(f"Rows: {res['rows']} | Truncated: {res['truncated']}")
                except Exception as e:
                    st.json(res)
            # Show chart
            if msg.get("chart"):
                try:
                    fig = go.Figure(msg["chart"])
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.error(f"Chart render failed: {e}")
                    # Try px
                    try:
                        import json as _json
                        st.json(msg["chart"])
                    except:
                        pass

    # Input
    # Handle pending query from sidebar examples
    default_query = ""
    if "pending_query" in st.session_state and st.session_state["pending_query"]:
        default_query = st.session_state["pending_query"]
        st.session_state["pending_query"] = None

    with st.form("chat_form", clear_on_submit=True):
        query = st.text_input("Your question", value=default_query, placeholder="e.g., Show top 5 products by sales or Monthly trend...")
        submitted = st.form_submit_button("Send 🚀", type="primary")

    if submitted and query:
        # Add user message immediately
        st.session_state["messages"].append({"role": "user", "content": query})
        with st.spinner("🤔 Analyzing... generating code & chart..."):
            resp = chat_query(dataset_id, query, st.session_state["conversation_id"])
            if resp is None:
                st.error("Backend unreachable")
            elif resp.status_code == 200:
                data = resp.json()
                # Update conversation id
                st.session_state["conversation_id"] = data["conversation_id"]
                # Append assistant
                st.session_state["messages"].append({
                    "role": "assistant",
                    "insight": data["insight"],
                    "code": data["generated_code"],
                    "code_explanation": data["code_explanation"],
                    "result": data["result"],
                    "chart": data["chart"],
                    "error": data["error"],
                    "stdout": data["stdout"],
                    "intent": data["intent"],
                })
                st.rerun()
            else:
                st.error(f"Chat failed ({resp.status_code}): {resp.text[:1000]}")
                # Add error as assistant message for visibility
                st.session_state["messages"].append({
                    "role": "assistant",
                    "insight": f"❌ Error: {resp.text[:500]}",
                    "code": "",
                    "code_explanation": "",
                    "result": None,
                    "chart": None,
                    "error": resp.text[:1000],
                    "stdout": "",
                })
                st.rerun()

    # Clear chat
    if st.session_state["messages"]:
        if st.button("🧹 Clear Chat"):
            st.session_state["messages"] = []
            st.session_state["conversation_id"] = None
            st.rerun()
