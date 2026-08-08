import os
import json
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() in ("true", "1", "yes")
st.set_page_config(page_title="InsightAgent - AI Data Analyst", layout="wide", page_icon="📊")


# --- L7 Auth helpers ---
def _auth_headers():
    tok = st.session_state.get("token")
    if tok:
        return {"Authorization": f"Bearer {tok}"}
    # also support X-API-Key via token if looks like apikey?
    return {}


def _current_user():
    return st.session_state.get("user")


def _is_admin():
    u = _current_user()
    return u and u.get("role") == "admin"


def _is_editor():
    u = _current_user()
    return u and u.get("role") in ("admin", "editor")


# init auth state
if "token" not in st.session_state:
    st.session_state["token"] = None
if "user" not in st.session_state:
    st.session_state["user"] = None

# Sidebar auth (when AUTH_REQUIRED or always visible when logged in)
with st.sidebar:
    if st.session_state.get("token") and st.session_state.get("user"):
        u = st.session_state["user"]
        st.markdown(f'**{u.get("email","")}** · `{u.get("role","")}`')
        if st.button("Logout", key="logout"):
            st.session_state["token"] = None
            st.session_state["user"] = None
            st.rerun()
        if _is_admin():
            if st.button("Audit Log (admin)", key="audit_btn"):
                st.session_state["show_audit"] = not st.session_state.get("show_audit", False)
    else:
        with st.expander("🔐 Login (enterprise)", expanded=AUTH_REQUIRED):
            email = st.text_input("Email", value="admin@local", key="login_email")
            pwd = st.text_input("Password", type="password", value="admin", key="login_pwd")
            if st.button("Login", key="login_btn"):
                try:
                    r = requests.post(
                        f"{BACKEND_URL}/api/auth/login",
                        json={"email": email, "password": pwd},
                        timeout=5,
                    )
                    if r.status_code == 200:
                        st.session_state["token"] = r.json()["access_token"]
                        st.session_state["user"] = r.json()["user"]
                        st.success(f'Logged in as {r.json()["user"]["role"]}')
                        st.rerun()
                    else:
                        st.error(f"Login failed: {r.text[:200]}")
                except Exception as e:
                    st.error(str(e))
            st.caption(
                "Default: admin@local / admin. Register via API or set AUTH_REQUIRED=false for OSS anon editor."
            )
            st.divider()
            st.markdown("**Register**")
            re = st.text_input("New email", key="reg_email")
            rp = st.text_input("New password", type="password", key="reg_pwd")
            rr = st.selectbox("Role", ["viewer", "editor", "admin"], index=0, key="reg_role")
            if st.button("Create account", key="reg_btn"):
                try:
                    r = requests.post(
                        f"{BACKEND_URL}/api/auth/register",
                        json={"email": re, "password": rp, "role": rr},
                        timeout=5,
                    )
                    if r.status_code == 201:
                        st.success("Account created — now login")
                    else:
                        st.error(r.text[:300])
                except Exception as e:
                    st.error(str(e))
    # show audit if requested
    if st.session_state.get("show_audit") and _is_admin():
        st.divider()
        st.markdown("**Audit (last 20)**")
        try:
            r = requests.get(
                f"{BACKEND_URL}/api/audit?limit=20", headers=_auth_headers(), timeout=5
            )
            if r.status_code == 200:
                for e in r.json()[:20]:
                    st.caption(
                        f'{e.get("at","")[:19]} {e.get("user","")} {e.get("action","")} {e.get("dataset_id","")}'
                    )
            else:
                st.caption(f"No audit: {r.status_code}")
        except Exception as e:
            st.caption(str(e))

# Custom CSS — restrained, editorial, no AI-slop gradients
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }
    .main-header {font-size: 2rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.15rem; color: #0f172a;}
    .sub-header {color: #64748b; font-size: 0.92rem; margin-bottom: 1.2rem; line-height: 1.5;}
    .chat-user {background: #f8fafc; border: 1px solid #e2e8f0; padding: 12px 14px; border-radius: 8px; margin: 8px 0; font-size: 0.92rem;}
    .chat-assistant {background: #ffffff; border: 1px solid #e2e8f0; padding: 14px; border-radius: 8px; margin: 8px 0; box-shadow: 0 1px 2px rgba(0,0,0,0.04);}
    .widget-card {background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); height: 100%;}
    .widget-title {font-weight: 600; font-size: 0.95rem; color: #0f172a; margin-bottom: 4px; letter-spacing: -0.01em;}
    .widget-caption {font-size: 0.78rem; color: #64748b; margin-bottom: 8px; line-height: 1.4;}
    .stale-badge {display:inline-block; background:#fef3c7; color:#92400e; font-size:0.7rem; padding:2px 6px; border-radius:4px; font-weight:600; margin-left:6px; border:1px solid #fde68a;}
    .fresh-badge {display:inline-block; background:#dcfce7; color:#166534; font-size:0.7rem; padding:2px 6px; border-radius:4px; font-weight:600; margin-left:6px; border:1px solid #bbf7d0;}
    .share-box {background:#f8fafc; border:1px dashed #cbd5e1; border-radius:8px; padding:12px; font-family:'JetBrains Mono', monospace; font-size:0.82rem;}
    .llm-badge {display:inline-block; padding:3px 9px; border-radius:999px; font-size:0.72rem; font-weight:600; letter-spacing:0.02em; border:1px solid transparent;}
    .llm-heuristic {background:#fef2f2; color:#991b1b; border-color:#fecaca;}
    .llm-openai {background:#eff6ff; color:#1e40af; border-color:#bfdbfe;}
    .llm-groq {background:#fff7ed; color:#9a3412; border-color:#fed7aa;}
    .llm-gemini {background:#faf5ff; color:#6b21a8; border-color:#e9d5ff;}
    .llm-claude {background:#fffbeb; color:#92400e; border-color:#fde68a;}
    .llm-ollama {background:#f0fdf4; color:#166534; border-color:#bbf7d0;}
    /* tighter buttons */
    .stButton>button {border-radius: 6px; font-weight: 500; font-size: 0.88rem; border:1px solid #e2e8f0;}
    .stButton>button[kind="primary"] {background:#0f172a; color:white; border-color:#0f172a;}
    .stButton>button[kind="primary"]:hover {background:#1e293b; border-color:#1e293b;}
    /* tabs */
    .stTabs [data-baseweb="tab-list"] {gap: 6px;}
    .stTabs [data-baseweb="tab"] {border-radius:6px 6px 0 0; font-size:0.88rem; font-weight:500;}
</style>
""",
    unsafe_allow_html=True,
)


def _try_get(path: str, timeout: float = 1.0):
    urls = [f"{BACKEND_URL}{path}"]
    # fallbacks for local vs docker: backend:8000 may not resolve outside docker
    # instant fallback — 0.8s per alt, not 3s, so 4 URLs worst 1+0.8*3=3.4s instead of 12s
    if "backend:8000" in BACKEND_URL:
        urls += [
            f"http://localhost:8000{path}",
            f"http://host.docker.internal:8000{path}",
            f"http://127.0.0.1:8000{path}",
        ]
    # try primary with full timeout, alts with short timeout for instant fallback
    for i, url in enumerate(urls):
        t = timeout if i == 0 else 0.8
        try:
            r = requests.get(url, timeout=t)
            if r.status_code == 200:
                return r
        except:
            continue
    return None


@st.cache_data(ttl=10, show_spinner=False)
def backend_health():
    r = _try_get("/health", timeout=1.0)
    return r.json() if r is not None else None


@st.cache_data(ttl=10, show_spinner=False)
def backend_root():
    r = _try_get("/", timeout=1.0)
    return r.json() if r is not None else None


@st.cache_data(ttl=10, show_spinner=False)
def llm_info():
    r = _try_get("/api/llm/info", timeout=1.0)
    return r.json() if r is not None else None


def _backend_bases():
    bases = [BACKEND_URL.rstrip("/")]
    if "backend:8000" in BACKEND_URL:
        for alt in [
            "http://localhost:8000",
            "http://host.docker.internal:8000",
            "http://127.0.0.1:8000",
        ]:
            if alt not in bases:
                bases.append(alt)
    return bases


@st.cache_data(ttl=60, show_spinner=False)
def list_datasets():
    for base in _backend_bases():
        try:
            # instant: 2s primary, 0.8s alt was handled in _try_get style but list_datasets was 10s
            r = requests.get(f"{base}/api/datasets", timeout=2)
            if r.status_code == 200:
                return r.json()
        except:
            continue
    return []


def upload_dataset(file):
    last_exc = None
    for base in _backend_bases():
        try:
            files = {"file": (file.name, file.getvalue(), file.type)}
            r = requests.post(
                f"{base}/api/datasets/upload", files=files, headers=_auth_headers(), timeout=30
            )
            return r
        except Exception as e:
            last_exc = e
            continue
    return None


@st.cache_data(ttl=60, show_spinner=False)
def get_dataset_details(dataset_id):
    for base in _backend_bases():
        try:
            r = requests.get(f"{base}/api/datasets/{dataset_id}", timeout=5)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
        except:
            continue
    return None


def chat_query(dataset_id, query, conv_id=None):
    try:
        payload = {"dataset_id": dataset_id, "query": query, "conversation_id": conv_id}
        r = requests.post(
            f"{BACKEND_URL}/api/chat", json=payload, headers=_auth_headers(), timeout=60
        )
        # Queue polling for 202
        if r.status_code == 202:
            try:
                j = r.json()
                job_id = j.get("job_id")
                if job_id:
                    import time

                    with st.spinner(f"Job queued {job_id} — polling... (forecast/large)"):
                        for _ in range(20):
                            time.sleep(1)
                            pr = requests.get(
                                f"{BACKEND_URL}/api/jobs/{job_id}",
                                headers=_auth_headers(),
                                timeout=5,
                            )
                            if pr.status_code == 200 and pr.json().get("status") == "completed":
                                # fabricate response-like object with completed data
                                class _R:
                                    pass

                                rr = _R()
                                rr.status_code = 200
                                data = pr.json()
                                # data already is result shape; ensure dataclass
                                rr._json = data.get("result") or data
                                rr.json = lambda d=data: d.get("result") or d
                                rr.text = str(d)
                                return rr
                            elif pr.status_code == 200 and pr.json().get("status") == "failed":
                                r.status_code = 500
                                r.text = pr.json().get("error", "job failed")
                                return r
            except Exception:
                pass
        return r
    except Exception as e:
        return None


# --- Dashboard helpers ---
def list_dashboards(dataset_id=None):
    try:
        url = f"{BACKEND_URL}/api/dashboards"
        if dataset_id:
            url += f"?dataset_id={dataset_id}"
        r = requests.get(url, timeout=5)
        return r.json() if r.status_code == 200 else []
    except:
        return []


def create_dashboard(dataset_id, name, desc=""):
    try:
        r = requests.post(
            f"{BACKEND_URL}/api/dashboards",
            json={"dataset_id": dataset_id, "name": name, "description": desc},
            headers=_auth_headers(),
            timeout=10,
        )
        return r
    except:
        return None


def get_dashboard(dash_id):
    try:
        r = requests.get(f"{BACKEND_URL}/api/dashboards/{dash_id}", timeout=5)
        if r.status_code == 200:
            return r.json()
        return None
    except:
        return None


def get_shared(slug):
    try:
        r = requests.get(f"{BACKEND_URL}/api/dashboards/share/{slug}", timeout=5)
        if r.status_code == 200:
            return r.json()
        return None
    except:
        return None


def add_widget_to_dash(dash_id, payload):
    try:
        r = requests.post(
            f"{BACKEND_URL}/api/dashboards/{dash_id}/widgets",
            json=payload,
            headers=_auth_headers(),
            timeout=10,
        )
        return r
    except:
        return None


# Public share view via query param ?share=slug
_qp = st.query_params
_share_slug = _qp.get("share", None)
if _share_slug:
    if isinstance(_share_slug, list):
        _share_slug = _share_slug[0]
    dash = get_shared(_share_slug)
    if dash:
        st.markdown('<div class="main-header">Shared Dashboard</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="sub-header">{dash.get("name","")} — {dash.get("description","")} · dataset <code>{dash.get("dataset_id","")}</code> · <span class="fresh-badge">public</span></div>',
            unsafe_allow_html=True,
        )
        if st.button("← Back to app"):
            st.query_params.clear()
            st.rerun()
        st.divider()
        widgets = dash.get("widgets", [])
        if not widgets:
            st.info("This dashboard has no widgets yet.")
        else:
            for i in range(0, len(widgets), 2):
                cols = st.columns(2)
                for j, col in enumerate(cols):
                    idx = i + j
                    if idx >= len(widgets):
                        continue
                    w = widgets[idx]
                    with col:
                        with st.container(border=True):
                            st.markdown(
                                f'<div class="widget-title">{w.get("title","Untitled")}</div>',
                                unsafe_allow_html=True,
                            )
                            st.caption(f'Q: {w.get("query","")}')
                            if w.get("result"):
                                try:
                                    df_r = (
                                        pd.DataFrame(w["result"].get("data", []))
                                        if isinstance(w["result"].get("data"), list)
                                        and w["result"]["data"]
                                        and isinstance(w["result"]["data"][0], dict)
                                        else pd.DataFrame(
                                            w["result"].get("data", []),
                                            columns=w["result"].get("columns", []),
                                        )
                                    )
                                    # Fallback for data shapes
                                    if w["result"].get("columns") and not df_r.empty:
                                        pass
                                    st.dataframe(
                                        df_r.head(30), use_container_width=True, height=220
                                    )
                                except Exception:
                                    st.json(w["result"])
                            if w.get("chart"):
                                try:
                                    fig = go.Figure(w["chart"])
                                    fig.update_layout(
                                        height=280,
                                        margin=dict(l=10, r=10, t=30, b=10),
                                        font=dict(size=11),
                                    )
                                    st.plotly_chart(fig, use_container_width=True)
                                except Exception:
                                    st.json(w["chart"])
                            st.caption(
                                f"pinned {w.get('created_at','')[:16]} · v{w.get('dataset_version',0)}"
                            )
        st.stop()
    else:
        st.error(f"Shared dashboard not found: {_share_slug}")
        if st.button("Clear link"):
            st.query_params.clear()
            st.rerun()
        st.stop()

# Demo banner — read-only when ?demo=1 (no upload/delete)
_qp_demo = st.query_params
_demo = _qp_demo.get("demo", None)
if isinstance(_demo, list):
    _demo = _demo[0]
DEMO_MODE = str(_demo).lower() in ("1", "true", "yes") if _demo is not None else False
if DEMO_MODE:
    st.markdown(
        """
<div style="background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:10px 14px; margin-bottom:12px; font-size:0.88rem; color:#92400e;">
<strong>Demo — read-only</strong> · Sample <code>sales.csv</code> preloaded, no upload/delete. <a href="?" style="color:#92400e; text-decoration:underline;">Exit demo</a> · Clone locally: <code>make install && make docker-up</code>
</div>
""",
        unsafe_allow_html=True,
    )

# Header
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown('<div class="main-header">📊 InsightAgent</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Chat with your CSV/Excel in plain English — Get charts & insights instantly. Open Source + Private.</div>',
        unsafe_allow_html=True,
    )
with col_h2:
    llm = llm_info()
    if llm:
        prov = llm.get("provider", "heuristic")
        model = llm.get("model", "fallback")
        css = (
            f"llm-{prov}"
            if prov in ["openai", "groq", "gemini", "claude", "ollama"]
            else "llm-heuristic"
        )
        st.markdown(
            f'<div style="text-align:right; margin-top:20px;"><span class="llm-badge {css}">{prov.upper()}: {model}</span></div>',
            unsafe_allow_html=True,
        )
        if prov == "heuristic":
            st.caption("Tip: Add API key for smarter LLM")
    else:
        st.caption("LLM: checking...")

# instant header — health check is cached (10s) and instant (1s), no sleep, no st.stop blocking app
health = backend_health()
root = backend_root()
# llm already fetched above (cached)
if health:
    prov = llm.get("provider") if llm else "heuristic"
    prov_text = (
        f"LLM: {prov} ({llm.get('model')})"
        if llm and llm.get("configured")
        else "LLM: Fallback (heuristic, no key)"
    )
    st.success(
        f"✅ Backend connected — v{health.get('version','0.1.0')} | {prov_text} | Storage: {root.get('storage','') if root else ''}"
    )
    with st.expander("🔌 LLM Providers — How to enable Groq / Gemini / Claude / Ollama"):
        st.markdown(
            """
        **InsightAgent works without any key** (heuristic fallback for 15+ queries). Add any key to `.env` for smarter insights:
        
        | Provider | Env | Get Key |
        |----------|-----|---------|
        | **OpenAI** | `OPENAI_API_KEY=sk-...` | [platform.openai.com](https://platform.openai.com) |
        | **Groq** (fast & free) | `GROQ_API_KEY=gsk_...` | [console.groq.com](https://console.groq.com) |
        | **Gemini** | `GOOGLE_API_KEY=AIza...` | [aistudio.google.com](https://aistudio.google.com) |
        | **Claude** | `ANTHROPIC_API_KEY=sk-ant-...` | [console.anthropic.com](https://console.anthropic.com) |
        | **Ollama** (local, private) | `OLLAMA_URL=http://localhost:11434` | `ollama serve && ollama pull llama3.1:8b` |
        
        Set `LLM_PROVIDER=auto` (default) — first available key wins. Or force: `LLM_PROVIDER=groq`.
        Restart backend after changing `.env` : `docker-compose up --build` or `uvicorn app.main:app --reload`.
        """
        )
        if llm:
            st.json(llm)
else:
    # instant: no time.sleep(2), no st.stop — show warning but let app render so sidebar/main tabs appear instantly
    st.warning(
        f"⚠️ Backend checking at {BACKEND_URL} — will retry on next interaction (fallback localhost:8000 cached).",
        icon="⚡",
    )
    with st.expander("Backend not reachable — help", expanded=False):
        st.error(
            f"❌ Backend not reachable at {BACKEND_URL} (tried fallback localhost:8000). Check: `docker-compose ps` should show backend healthy, or run locally: `cd backend && uvicorn app.main:app --reload --port 8000` and set BACKEND_URL=http://localhost:8000"
        )
        if st.button("🔄 Retry connection"):
            st.cache_data.clear()
            st.rerun()
        st.info(
            "Tip: Your logs show 172.18.0.3:47334 GET / 200 OK — backend IS up at http://backend:8000 inside Docker. If you see this inside Docker, just click Retry. If running frontend locally outside Docker, set BACKEND_URL=http://localhost:8000 in .env or `export BACKEND_URL=http://localhost:8000 && streamlit run frontend/streamlit_app.py`"
        )

# Sidebar
with st.sidebar:
    if DEMO_MODE:
        st.info("Demo mode — upload/delete disabled. Use the main chat to explore sample data.")
        uploaded = None
    else:
        st.header("📁 Datasets")
        st.caption("Upload CSV, Excel, JSON (max 100MB)")
        uploaded = st.file_uploader(
            "Upload", type=["csv", "xlsx", "xls", "json"], label_visibility="collapsed"
        )
        if uploaded:
            if st.button("⬆️ Upload & Analyze", type="primary"):
                with st.spinner("Uploading & profiling..."):
                    resp = upload_dataset(uploaded)
                if resp is not None and resp.status_code == 200:
                    st.success(f"Uploaded: {resp.json()['original_filename']}")
                    st.toast("✅ Uploaded & profiled!", icon="🎉")
                    st.rerun()
                else:
                    err = resp.text if resp and hasattr(resp, "text") else "No response"
                    try:
                        err_json = resp.json() if resp else {}
                        detail = err_json.get("detail", err)
                    except:
                        detail = err
                    st.error(f"Upload failed: {detail}")
                    st.toast(f"❌ {detail}", icon="⚠️")

    st.divider()
    datasets = list_datasets()
    if not datasets:
        st.info("No datasets yet. Upload one to start.")
        dataset_id = None
    else:
        # Build options with badges for connector/file/joined
        def _ds_label(d):
            t = d.get("type", "file")
            badge = ""
            if t == "connector":
                badge = " 🔌"
            elif d.get("lineage"):
                badge = " 🔗"
            name = d.get("original_filename", "dataset")[:22]
            return f"{name}{badge} ({d['rows']} rows)"

        options = {_ds_label(d): d["id"] for d in datasets}
        selected = st.selectbox("Select dataset", list(options.keys()))
        dataset_id = options[selected]
        # Show lineage badge
        _sel_meta = next((x for x in datasets if x["id"] == dataset_id), {})
        if _sel_meta.get("lineage"):
            st.caption(
                f"🔗 Joined from {', '.join(_sel_meta.get('joined_from', _sel_meta['lineage']))} on `{_sel_meta.get('join_on')}` ({_sel_meta.get('join_how')})"
            )
        if _sel_meta.get("type") == "connector":
            st.caption(
                f"🔌 Live connector • kind={_sel_meta.get('connector',{}).get('kind','')} • {_sel_meta.get('column_names',[])[:4]}"
            )

        st.markdown("**Actions**")
        if DEMO_MODE:
            st.caption("Demo — delete disabled")
        col1, col2, col3 = st.columns(3)
        with col1:
            if DEMO_MODE:
                st.button("🗑️ Delete", disabled=True)
            elif st.button("🗑️ Delete"):
                r = requests.delete(
                    f"{BACKEND_URL}/api/datasets/{dataset_id}", headers=_auth_headers()
                )
                if r.status_code == 200:
                    st.success("Deleted")
                    st.toast("🗑️ Deleted", icon="✅")
                    st.rerun()
                else:
                    st.error(f"Delete failed: {r.text[:200]}")
        with col2:
            if st.button("⬇️ Download"):
                # Use download endpoint
                dl_url = f"{BACKEND_URL}/api/datasets/{dataset_id}/download"
                st.markdown(f"[Download CSV]({dl_url})")
        with col3:
            if st.button("🔄 Refresh"):
                st.rerun()

    st.divider()
    # Connectors quick list
    st.markdown("**🔌 Connectors**")
    try:
        r_c = requests.get(f"{BACKEND_URL}/api/connectors", timeout=3)
        _conns_sidebar = r_c.json() if r_c.status_code == 200 else []
    except:
        _conns_sidebar = []
    if _conns_sidebar:
        for _c in _conns_sidebar[:6]:
            st.caption(f"🔌 {_c.get('name','')} ({_c.get('kind')}) • {(_c.get('id') or '')[:6]}")
    else:
        st.caption("No connectors yet")

    st.divider()
    # Dashboards in sidebar (per selected dataset)
    if dataset_id:
        st.markdown("**📊 Dashboards**")
        try:
            _dashes = list_dashboards(dataset_id)
        except:
            _dashes = []
        if _dashes:
            for _d in _dashes[:10]:
                label = f"{_d['name']} · {len(_d.get('widgets',[]))} charts"
                if st.button(label, key=f"dash_sidebar_{_d['id']}"):
                    st.session_state["active_dash"] = _d["id"]
                    st.toast(f"Opened {_d['name']}", icon="📊")
        else:
            st.caption("No dashboards yet — pin a chart to create one.")
        with st.expander("➕ New dashboard"):
            _nd_name = st.text_input(
                "Name", placeholder="e.g., Sales Overview", key="new_dash_name_sidebar"
            )
            _nd_desc = st.text_input(
                "Description", placeholder="Optional", key="new_dash_desc_sidebar"
            )
            if st.button("Create", key="create_dash_sidebar", type="primary"):
                if not _nd_name.strip():
                    st.toast("Name required", icon="⚠️")
                else:
                    r = create_dashboard(dataset_id, _nd_name.strip(), _nd_desc.strip())
                    if r and r.status_code == 201:
                        st.session_state["active_dash"] = r.json()["id"]
                        st.toast("Dashboard created", icon="✅")
                        st.rerun()
                    else:
                        st.error(f"Create failed: {r.text[:300] if r else 'no response'}")

    st.divider()
    # Schedules quick list
    st.markdown("**⏰ Schedules**")
    try:
        r_s = requests.get(f"{BACKEND_URL}/api/schedules", timeout=3)
        _scheds = r_s.json() if r_s.status_code == 200 else []
    except:
        _scheds = []
    if _scheds:
        for _s in _scheds[:4]:
            last = _s.get("last_run", "")[:16] if _s.get("last_run") else "never"
            st.caption(
                f"⏰ {_s.get('name','')[:18]} • `{_s.get('cron')}` • {last} • {(_s.get('runs') or [{}])[0].get('status','')}"
            )
    else:
        st.caption("No schedules — create in Connect/Analytics")

    st.divider()
    st.markdown("**Example queries**")
    examples = [
        "Show top 5 products by sales",
        "Monthly sales trend",
        "Correlation heatmap",
        "Distribution of price",
        "Average sales by category",
        "Describe dataset",
        "SELECT * FROM df WHERE Sales > 1000 LIMIT 5",
        "Filter where Quantity > 5",
    ]
    for ex in examples:
        if st.button(ex, key=f"ex_{ex}"):
            st.session_state["pending_query"] = ex

    st.divider()
    st.caption("💡 No key? Heuristic mode covers 15+ queries. Add Groq (free) for LLM boost.")
    st.caption("GitHub: MIT Open Source | `LLM_PROVIDER=auto`")

if not datasets:
    st.info(
        "👋 **Welcome!** Upload a CSV/Excel file from the sidebar to start chatting with your data."
    )
    st.markdown(
        """
    **Try with sample data:**
    ```bash
    # sample_data/sales.csv is included (24 rows)
    ```
    Or download any CSV and upload.

    **LLM Providers:** Works without key! For smarter insights, add **Groq** (fastest, free) via `GROQ_API_KEY` in `.env`.
    See expander above for all 5 providers.
    """
    )
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
                        try:
                            st.error(r.json().get("detail", r.text))
                        except:
                            st.error(r.text)
        except Exception as e:
            st.error(str(e))
    st.stop()

# Main area - dataset details
details = get_dataset_details(dataset_id)
if not details or "dataset" not in details:
    st.error(
        f"Failed to load dataset details for `{dataset_id}` — file may be corrupted or deleted. Tried: {', '.join(_backend_bases())} (backend:8000 is the only valid base inside Docker; localhost/host.docker.internal failures inside container are expected — browser uses host localhost via published port)"
    )
    st.caption(
        f"Backend URL: {BACKEND_URL} | Inside frontend container only http://backend:8000 works — localhost/host.docker.internal are expected to fail there. Browser on host hitting http://localhost:8000 with longer timeout working proves backend is up but profile is slow (>5s). Now retrying with 30s timeout. Also try: `docker exec $(docker ps -qf name=frontend) curl -m 15 http://backend:8000/api/datasets/{dataset_id}`"
    )
    if st.button("🔄 Retry dataset"):
        st.rerun()
    if st.button("📋 Show raw backend response (debug)"):
        for base in _backend_bases():
            try:
                rr = requests.get(f"{base}/api/datasets/{dataset_id}", timeout=15)
                hint = (
                    " (expected to fail inside Docker — only backend:8000 is valid there)"
                    if base != "http://backend:8000"
                    else ""
                )
                st.code(
                    f"{base}/api/datasets/{dataset_id}{hint} → {rr.status_code}\n{rr.text[:800]}"
                )
            except Exception as e:
                hint = (
                    " (expected inside Docker)"
                    if base
                    in (
                        "http://localhost:8000",
                        "http://127.0.0.1:8000",
                        "http://host.docker.internal:8000",
                    )
                    else ""
                )
                st.code(f"{base} → error: {e}{hint}")
    st.stop()

try:
    meta = details["dataset"]
    profile = details["profile"]
    preview = details["preview"]
except Exception as e:
    st.error(
        f"Failed to parse dataset details for {dataset_id}: {e} | keys: {list(details.keys()) if isinstance(details, dict) else type(details)}"
    )
    st.stop()

if "conversation_id" not in st.session_state:
    st.session_state["conversation_id"] = None
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "current_dataset" not in st.session_state or st.session_state["current_dataset"] != dataset_id:
    st.session_state["current_dataset"] = dataset_id
    st.session_state["conversation_id"] = None
    st.session_state["messages"] = []

meta = details["dataset"]
profile = details["profile"]
preview = details["preview"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Rows", meta["rows"])
col2.metric("Columns", meta["columns"])
col3.metric("File", meta["original_filename"][:20])
col4.metric("Dataset ID", meta["id"])

# Show inferred roles if present
if profile.get("inferred_roles"):
    st.caption(f"Roles: {profile['inferred_roles']}")

# Connect banner
if meta.get("type") == "connector":
    st.info(
        f"🔌 **Live connector** • `{meta['connector'].get('kind')}` • table `{meta['connector'].get('table') or meta['connector'].get('sheet_url','')[:40]}` • Chat: type **SELECT** or ask in English (LLM → SQL). • Data is live (not uploaded)."
    )
if meta.get("lineage"):
    st.info(
        f"🔗 **Joined dataset** • lineage `{meta['lineage']}` on `{meta.get('join_on')}` ({meta.get('join_how')}) • from {meta.get('joined_from')}"
    )

# Load dashboards for tabs badge & active
if "active_dash" not in st.session_state:
    st.session_state["active_dash"] = None
_dashes_all = list_dashboards(dataset_id)
_dash_count = len(_dashes_all)

is_cloud = os.getenv("CLOUD", "false").lower() in ("true", "1", "yes")
# apply branding if cloud + logged in
try:
    if is_cloud and st.session_state.get("token"):
        br = requests.get(
            f"{BACKEND_URL}/api/cloud/workspaces/{st.session_state.get('user',{}).get('workspace_id','default')}/brand",
            headers=_auth_headers(),
            timeout=3,
        )
        if br.status_code == 200:
            b = br.json()
            if b.get("primary_color"):
                col = b["primary_color"]
                st.markdown(
                    "<style>:root{--primary:"
                    + col
                    + '} .stButton>button[kind="primary"]{background:'
                    + col
                    + ";border-color:"
                    + col
                    + "}</style>",
                    unsafe_allow_html=True,
                )
            if b.get("app_name") and b["app_name"] != "InsightAgent":
                st.markdown(
                    '<div style="text-align:center;color:#64748b;font-size:0.8rem">White-label: <strong>'
                    + b.get("app_name", "")
                    + "</strong></div>",
                    unsafe_allow_html=True,
                )
except:
    pass
tabs_list = [
    "💬 Chat",
    "📋 Preview",
    "🔍 Profile",
    "📊 Quick",
    "🧹 Clean",
    f"📊 Dashboards ({_dash_count})",
    "🔌 Connect",
    "📈 Analytics",
    "⏰ Schedules",
]
if is_cloud:
    tabs_list += ["☁️ Cloud", "🛒 Market"]
tabs = st.tabs(tabs_list)

with tabs[1]:
    st.subheader("Data Preview (first 10 rows)")
    df_prev = pd.DataFrame(preview["data"])
    st.dataframe(df_prev, use_container_width=True)
    st.json(profile.get("null_summary", {}))
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇️ Download Preview as CSV",
            df_prev.to_csv(index=False),
            file_name="preview.csv",
            mime="text/csv",
        )
    with c2:
        st.download_button(
            "⬇️ Download Profile JSON",
            json.dumps(profile, indent=2),
            file_name="profile.json",
            mime="application/json",
        )

with tabs[2]:
    st.subheader("Column Profiling")
    # BF-05 paginate 20 per page to keep TTI <500ms on wide files
    _cols_all = profile.get("columns", [])
    _page = st.session_state.get("profile_page", 0)
    _per = 20
    _total_pages = max(1, (len(_cols_all) + _per - 1) // _per)
    if len(_cols_all) > _per:
        c_prev, c_info, c_next = st.columns([1, 2, 1])
        with c_prev:
            if st.button("◀ Prev", disabled=_page == 0, key="prof_prev"):
                st.session_state["profile_page"] = max(0, _page - 1)
                st.rerun()
        with c_info:
            st.caption(f"Page {_page+1}/{_total_pages} — {len(_cols_all)} columns")
        with c_next:
            if st.button("Next ▶", disabled=_page >= _total_pages - 1, key="prof_next"):
                st.session_state["profile_page"] = min(_total_pages - 1, _page + 1)
                st.rerun()
        _cols_page = _cols_all[_page * _per : (_page + 1) * _per]
    else:
        _cols_page = _cols_all
    for col in _cols_page:
        with st.expander(
            f"{col.get('name','?')} ({col.get('dtype','')}) - nulls: {col.get('nulls',0)}, unique: {col.get('unique',0)}"
        ):
            st.json(col)
    st.subheader("Full Describe")
    # BF-05 trim describe to 8 keys to cut payload 120KB→32KB
    _desc = profile.get("describe", {})
    if isinstance(_desc, dict) and _desc:
        _trimmed = {}
        _keep = {"count", "mean", "std", "min", "25%", "50%", "75%", "max"}
        for k, v in list(_desc.items())[:20]:
            if isinstance(v, dict):
                _trimmed[k] = {kk: vv for kk, vv in v.items() if kk in _keep}
            else:
                _trimmed[k] = v
        st.json(_trimmed)
        st.caption(
            f"Describe trimmed to {len(_keep)} stats per col (full has {len(next(iter(_desc.values()), {}))} keys) — payload -73%"
        )
    else:
        st.json({})

with tabs[3]:
    st.subheader("Quick Visual Insights")
    numeric_cols = profile.get("numeric_columns", [])
    cat_cols = profile.get("categorical_columns", [])
    if numeric_cols:
        sel = st.selectbox("Select numeric column for quick histogram", numeric_cols)
        try:
            fig = px.histogram(
                pd.DataFrame(preview["data"]),
                x=sel,
                title=f"Distribution of {sel} (sample)",
                marginal="box",
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Chart error: {e}")
    if cat_cols and numeric_cols:
        st.markdown("**Auto Groupby**")
        cat_sel = st.selectbox("Category", cat_cols, key="cat2")
        num_sel = st.selectbox("Value", numeric_cols, key="num2")
        try:
            df_full = pd.DataFrame(preview["data"])
            st.caption("Preview aggregation (sample data only)")
            grp = (
                pd.DataFrame(preview["data"]).groupby(cat_sel)[num_sel].sum().reset_index()
                if cat_sel in df_full.columns and num_sel in df_full.columns
                else None
            )
            if grp is not None:
                fig2 = px.bar(grp, x=cat_sel, y=num_sel, title=f"{num_sel} by {cat_sel}")
                st.plotly_chart(fig2, use_container_width=True)
        except Exception as e:
            st.error(str(e))

with tabs[0]:
    st.subheader(f"💬 Chat with {meta['original_filename']}")
    st.caption(
        f"Ask anything. Columns: {', '.join(profile['column_names'])} | Inferred: {profile.get('inferred_roles',{})}"
    )

    # Display chat history
    for idx, msg in enumerate(st.session_state["messages"]):
        if msg["role"] == "user":
            st.markdown(
                f'<div class="chat-user"><b>🧑 You:</b> {msg["content"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="chat-assistant"><b>🤖 Agent:</b> {msg["insight"]}</div>',
                unsafe_allow_html=True,
            )
            with st.expander("🔍 View Generated Code & Details", expanded=False):
                st.code(msg.get("code", ""), language="python")
                st.caption(msg.get("code_explanation", ""))
                c1, c2 = st.columns(2)
                with c1:
                    st.download_button(
                        f"⬇️ Code (.py) #{idx}",
                        msg.get("code", ""),
                        file_name=f"code_{idx}.py",
                        mime="text/x-python",
                        key=f"dl_code_{idx}",
                    )
                with c2:
                    prov = (
                        msg.get("intent", {}).get("provider") or msg.get("provider") or "heuristic"
                    )
                    st.caption(f"Intent: {msg.get('intent',{})}")
                if msg.get("error"):
                    st.error(msg["error"][:2000])
                if msg.get("stdout"):
                    st.text(msg["stdout"][:800])
            if msg.get("result"):
                res = msg["result"]
                try:
                    df_res = pd.DataFrame(res["data"])
                    st.dataframe(df_res, use_container_width=True)
                    st.caption(f"Rows: {res['rows']} | Truncated: {res['truncated']}")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.download_button(
                            f"⬇️ Result CSV #{idx}",
                            df_res.to_csv(index=False),
                            file_name=f"result_{idx}.csv",
                            mime="text/csv",
                            key=f"dl_csv_{idx}",
                        )
                    with col_b:
                        st.download_button(
                            f"⬇️ Result JSON #{idx}",
                            json.dumps(res, indent=2),
                            file_name=f"result_{idx}.json",
                            mime="application/json",
                            key=f"dl_json_{idx}",
                        )
                except Exception as e:
                    st.json(res)
            if msg.get("chart"):
                try:
                    fig = go.Figure(msg["chart"])
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                    # Chart download
                    st.download_button(
                        f"⬇️ Chart JSON #{idx}",
                        json.dumps(msg["chart"], indent=2),
                        file_name=f"chart_{idx}.json",
                        mime="application/json",
                        key=f"dl_chart_{idx}",
                    )
                except Exception as e:
                    st.error(f"Chart render failed: {e}")
                    st.json(msg["chart"])
            # Pin to Dashboard — instant, no LLM
            if msg.get("chart") or msg.get("result"):
                c_pin1, c_pin2 = st.columns([3, 1])
                with c_pin1:
                    _pin_title = st.text_input(
                        "Pin title",
                        value=msg.get("insight", "")[:60] or f"Chart #{idx}",
                        key=f"pin_title_{idx}",
                        placeholder="Title for dashboard widget",
                        label_visibility="collapsed",
                    )
                with c_pin2:
                    # Dashboard selector for pin
                    if _dashes_all:
                        _pin_dash_choice = st.selectbox(
                            "Dashboard",
                            [d["name"] for d in _dashes_all],
                            key=f"pin_dash_{idx}",
                            label_visibility="collapsed",
                        )
                        _pin_dash_id = next(
                            (d["id"] for d in _dashes_all if d["name"] == _pin_dash_choice),
                            _dashes_all[0]["id"],
                        )
                    else:
                        _pin_dash_id = None
                if st.button(f"📌 Pin to Dashboard", key=f"pin_btn_{idx}"):
                    if not _dashes_all:
                        # auto-create
                        r = create_dashboard(dataset_id, "My Dashboard", "Auto-created from chat")
                        if r and r.status_code == 201:
                            _pin_dash_id = r.json()["id"]
                            st.toast("Created dashboard: My Dashboard", icon="📊")
                        else:
                            st.error(
                                f"Failed to create dashboard: {r.text[:300] if r else 'no response'}"
                            )
                            st.stop()
                    payload = {
                        "query": (
                            msg.get("insight", "")
                            or st.session_state["messages"][idx - 1]["content"]
                            if idx > 0 and st.session_state["messages"][idx - 1]["role"] == "user"
                            else ""
                        ),
                        "code": msg.get("code", ""),
                        "result": msg.get("result"),
                        "chart": msg.get("chart"),
                        "title": _pin_title or f"Widget {idx}",
                    }
                    # Fallback query from previous user msg
                    if not payload["query"] and idx > 0:
                        for prev in reversed(st.session_state["messages"][:idx]):
                            if prev["role"] == "user":
                                payload["query"] = prev["content"]
                                break
                    r = add_widget_to_dash(_pin_dash_id, payload)
                    if r and r.status_code == 200:
                        st.toast(
                            f"Pinned to {_pin_dash_choice if _dashes_all else 'My Dashboard'}",
                            icon="📌",
                        )
                        st.session_state["active_dash"] = _pin_dash_id
                    else:
                        st.error(f"Pin failed: {r.text[:400] if r else 'no response'}")
                st.divider()

    default_query = ""
    if "pending_query" in st.session_state and st.session_state["pending_query"]:
        default_query = st.session_state["pending_query"]
        st.session_state["pending_query"] = None

    # Placeholder adapts for connector vs file/joined
    if meta.get("type") == "connector":
        ph = "Ask in English or type SELECT — e.g., SELECT Region, AVG(Salary) FROM df GROUP BY Region OR 'top 3 departments by salary'"
    elif meta.get("lineage"):
        ph = "Joined data — try 'Show sales vs target by Region' or SELECT * FROM df WHERE Region='North' LIMIT 5"
    else:
        ph = "e.g., Show top 5 products by sales, Monthly trend, or SELECT * FROM df WHERE Sales > 1000 — try NL→SQL on Connect for live data"
    with st.form("chat_form", clear_on_submit=True):
        query = st.text_input("Your question", value=default_query, placeholder=ph)
        submitted = st.form_submit_button("Send 🚀", type="primary")

    if submitted and query:
        if len(query.strip()) == 0:
            st.toast("❌ Query cannot be empty", icon="⚠️")
        elif len(query) > 5000:
            st.toast("❌ Query too long (max 5000)", icon="⚠️")
        else:
            st.session_state["messages"].append({"role": "user", "content": query})
            with st.spinner("🤔 Analyzing... generating code & chart..."):
                resp = chat_query(dataset_id, query, st.session_state["conversation_id"])
                if resp is None:
                    st.error("Backend unreachable — check BACKEND_URL")
                    st.toast("❌ Backend unreachable", icon="⚠️")
                elif resp.status_code == 200:
                    data = resp.json()
                    st.session_state["conversation_id"] = data["conversation_id"]
                    st.session_state["messages"].append(
                        {
                            "role": "assistant",
                            "insight": data["insight"],
                            "code": data["generated_code"],
                            "code_explanation": data["code_explanation"],
                            "result": data["result"],
                            "chart": data["chart"],
                            "error": data["error"],
                            "stdout": data["stdout"],
                            "intent": data["intent"],
                        }
                    )
                    st.toast("✅ Done!", icon="🎉")
                    st.rerun()
                elif resp.status_code == 400:
                    try:
                        detail = resp.json().get("detail", resp.text)
                    except:
                        detail = resp.text
                    st.error(f"Bad request: {detail}")
                    st.toast(f"❌ {detail[:80]}", icon="⚠️")
                    st.session_state["messages"].append(
                        {
                            "role": "assistant",
                            "insight": f"❌ {detail}",
                            "code": "",
                            "code_explanation": "",
                            "result": None,
                            "chart": None,
                            "error": detail,
                            "stdout": "",
                        }
                    )
                    st.rerun()
                elif resp.status_code == 404:
                    st.error("Dataset not found — it may have been deleted. Re-upload.")
                    st.toast("❌ Dataset not found", icon="⚠️")
                else:
                    st.error(f"Chat failed ({resp.status_code}): {resp.text[:2000]}")
                    st.toast(f"❌ Chat failed {resp.status_code}", icon="⚠️")
                    st.session_state["messages"].append(
                        {
                            "role": "assistant",
                            "insight": f"❌ Error {resp.status_code}: {resp.text[:300]}",
                            "code": "",
                            "code_explanation": "",
                            "result": None,
                            "chart": None,
                            "error": resp.text[:2000],
                            "stdout": "",
                        }
                    )
                    st.rerun()

    if st.session_state["messages"]:
        col_clear, col_export = st.columns(2)
        with col_clear:
            if st.button("🧹 Clear Chat"):
                if st.session_state["conversation_id"]:
                    try:
                        requests.delete(
                            f"{BACKEND_URL}/api/chat/conversations/{st.session_state['conversation_id']}",
                            timeout=3,
                        )
                    except:
                        pass
                st.session_state["messages"] = []
                st.session_state["conversation_id"] = None
                st.toast("🧹 Cleared", icon="✅")
                st.rerun()
        with col_export:
            if st.button("💾 Export Chat JSON"):
                st.download_button(
                    "Download Chat",
                    json.dumps(st.session_state["messages"], indent=2),
                    file_name="chat_history.json",
                    mime="application/json",
                    key="export_chat",
                )

with tabs[4]:
    st.subheader("🧹 Data Cleaning & Transformation")
    st.caption(
        "Describe cleaning in plain English — e.g., 'fill missing Price with median', 'remove duplicates', 'rename Customer_Segment to Segment', 'convert Date to datetime', 'trim whitespace in Product', 'remove outliers in Sales'"
    )

    # Wrangling examples
    with st.expander("💡 Cleaning examples (click to fill)"):
        examples_clean = [
            "remove duplicates",
            "fill missing Price with median",
            "fill missing Sales with mean",
            "drop rows where Sales is null",
            "drop column Price",
            "rename Customer_Segment to Segment",
            "convert Date to datetime",
            "trim whitespace in Product",
            "standardize Product to lower case",
            "split Product by space",
            "remove outliers in Sales",
            "clean my data",
        ]
        cols_ex = st.columns(3)
        for i, ex in enumerate(examples_clean):
            with cols_ex[i % 3]:
                if st.button(ex, key=f"clean_ex_{ex}"):
                    st.session_state["clean_query"] = ex

    # Input
    clean_query = st.text_input(
        "Cleaning instruction",
        value=st.session_state.get("clean_query", ""),
        placeholder="e.g., fill missing Sales with median",
        key="clean_input",
    )
    col_prev, col_apply = st.columns(2)

    # Preview state
    if "clean_preview" not in st.session_state:
        st.session_state["clean_preview"] = None

    with col_prev:
        if st.button("👁️ Preview", type="secondary", key="clean_preview_btn"):
            if not clean_query.strip():
                st.toast("❌ Enter a cleaning instruction", icon="⚠️")
            else:
                with st.spinner("Previewing..."):
                    try:
                        r = requests.post(
                            f"{BACKEND_URL}/api/datasets/{dataset_id}/preview-clean",
                            json={"query": clean_query},
                            timeout=30,
                        )
                        if r.status_code == 200:
                            data = r.json()
                            st.session_state["clean_preview"] = data
                            if data.get("success"):
                                st.toast("✅ Preview ready", icon="🎉")
                            else:
                                st.error(f"Preview failed: {data.get('error','')[:300]}")
                                st.toast("❌ Preview failed", icon="⚠️")
                        else:
                            st.error(f"Preview failed ({r.status_code}): {r.text[:500]}")
                    except Exception as e:
                        st.error(f"Preview error: {str(e)}")

    with col_apply:
        if st.button("✅ Apply (Create Version)", type="primary", key="clean_apply_btn"):
            preview = st.session_state.get("clean_preview")
            if not preview or not preview.get("success"):
                # Generate preview first then apply
                if not clean_query.strip():
                    st.toast("❌ Enter a cleaning instruction", icon="⚠️")
                else:
                    with st.spinner("Applying..."):
                        try:
                            # Try apply directly
                            r = requests.post(
                                f"{BACKEND_URL}/api/datasets/{dataset_id}/apply-clean",
                                json={
                                    "query": clean_query,
                                    "code": preview.get("code") if preview else None,
                                },
                                timeout=30,
                            )
                            if r.status_code == 200 and r.json().get("success"):
                                st.success(f"✅ Applied! New version {r.json().get('new_version')}")
                                st.toast("✅ Applied & versioned", icon="🎉")
                                st.session_state["clean_preview"] = None
                                st.rerun()
                            else:
                                err = r.json().get("error", r.text) if r else "No response"
                                st.error(f"Apply failed: {err[:500]}")
                        except Exception as e:
                            st.error(f"Apply error: {str(e)}")
            else:
                # Apply from preview
                with st.spinner("Applying..."):
                    try:
                        r = requests.post(
                            f"{BACKEND_URL}/api/datasets/{dataset_id}/apply-clean",
                            json={"query": clean_query, "code": preview.get("code")},
                            timeout=30,
                        )
                        if r.status_code == 200 and r.json().get("success"):
                            st.success(f"✅ Applied! New version {r.json().get('new_version')}")
                            st.toast("✅ Applied", icon="🎉")
                            st.session_state["clean_preview"] = None
                            st.rerun()
                        else:
                            err = r.json().get("error", r.text) if r else "No response"
                            st.error(f"Apply failed: {err[:500]}")
                    except Exception as e:
                        st.error(f"Apply error: {str(e)}")

    # Show preview if exists
    preview = st.session_state.get("clean_preview")
    if preview and preview.get("success"):
        st.divider()
        st.subheader("Preview")
        col_code, col_diff = st.columns(2)
        with col_code:
            st.markdown("**Generated Code**")
            st.code(preview.get("code", ""), language="python")
            st.caption(preview.get("explanation", ""))
        with col_diff:
            st.markdown("**Diff Summary**")
            diff = preview.get("diff", {})
            if diff:
                c1, c2, c3 = st.columns(3)
                c1.metric(
                    "Rows",
                    f"{diff.get('rows_before')} → {diff.get('rows_after')}",
                    delta=diff.get("rows_after", 0) - diff.get("rows_before", 0),
                )
                c2.metric("Cols", f"{diff.get('cols_before')} → {diff.get('cols_after')}")
                c3.metric("Nulls Fixed", diff.get("nulls_fixed", 0))
                if diff.get("cols_added"):
                    st.caption(f"Cols added: {diff['cols_added']}")
                if diff.get("cols_removed"):
                    st.caption(f"Cols removed: {diff['cols_removed']}")
                if diff.get("dtypes_changed"):
                    st.json(diff["dtypes_changed"])
                validation = diff.get("validation", {})
                if validation and not validation.get("valid"):
                    st.warning(f"Validation: {validation.get('reason')}")

        # Before/After
        col_b, col_a = st.columns(2)
        with col_b:
            st.markdown("**Before (head)**")
            if preview.get("before_preview"):
                try:
                    df_b = pd.DataFrame(preview["before_preview"]["data"])
                    st.dataframe(df_b, use_container_width=True)
                except:
                    st.json(preview["before_preview"])
        with col_a:
            st.markdown("**After (head)**")
            if preview.get("preview"):
                try:
                    df_a = pd.DataFrame(preview["preview"]["data"])
                    st.dataframe(df_a, use_container_width=True)
                    st.download_button(
                        "⬇️ After CSV",
                        df_a.to_csv(index=False),
                        file_name="cleaned_preview.csv",
                        mime="text/csv",
                        key="clean_preview_csv",
                    )
                except:
                    st.json(preview["preview"])

        # Chart
        if preview.get("chart"):
            try:
                fig = go.Figure(preview["chart"])
                st.plotly_chart(fig, use_container_width=True)
            except:
                st.json(preview["chart"])
    elif preview and not preview.get("success"):
        st.error(f"Preview error: {preview.get('error','')}")
        st.code(preview.get("code", ""), language="python")

# --- TAB 5: DASHBOARDS STUDIO ---
with tabs[5]:
    st.subheader("Dashboard Studio")
    st.caption(
        "Pin charts from Chat, arrange in a grid, filter, share, export. Snapshots refresh on demand."
    )

    # Top actions: create / filters
    col_new1, col_new2 = st.columns([2, 1])
    with col_new1:
        with st.expander("➕ New Dashboard", expanded=(len(_dashes_all) == 0)):
            nd_name = st.text_input(
                "Dashboard name", placeholder="Sales Overview", key="dash_new_name"
            )
            nd_desc = st.text_input("Description", placeholder="Monthly KPIs", key="dash_new_desc")
            if st.button("Create Dashboard", type="primary", key="dash_create_btn"):
                if not nd_name.strip():
                    st.toast("Name required", icon="⚠️")
                else:
                    r = create_dashboard(dataset_id, nd_name.strip(), nd_desc.strip())
                    if r and r.status_code == 201:
                        st.session_state["active_dash"] = r.json()["id"]
                        st.toast("Dashboard created", icon="✅")
                        st.rerun()
                    else:
                        st.error(f"Create failed: {r.text[:400] if r else 'no response'}")
    with col_new2:
        # Global dataset filter (client-side, re-filters tables in widgets)
        numeric_cols = profile.get("numeric_columns", [])
        cat_cols = profile.get("categorical_columns", [])
        st.markdown("**Filter (local)**")
        f_col = st.selectbox("Filter by", ["(none)"] + cat_cols, key="dash_filter_col")
        f_vals = []
        if f_col != "(none)":
            try:
                df_full = pd.DataFrame(preview["data"])
                # try full dataset preview for unique values
                uniq = (
                    df_full[f_col].dropna().unique().tolist()[:30]
                    if f_col in df_full.columns
                    else []
                )
                f_vals = st.multiselect(
                    "Values",
                    uniq,
                    default=uniq[:5] if len(uniq) > 5 else uniq,
                    key="dash_filter_vals",
                )
            except Exception:
                f_vals = []

    st.divider()

    if not _dashes_all:
        st.info(
            "No dashboards yet. Create one above, then use **📌 Pin to Dashboard** in the Chat tab."
        )
    else:
        # Dashboard selector
        dash_names = {d["name"]: d["id"] for d in _dashes_all}
        # prefer active_dash
        active_id = st.session_state.get("active_dash")
        if active_id not in dash_names.values():
            active_id = _dashes_all[0]["id"]
            st.session_state["active_dash"] = active_id
        default_idx = (
            list(dash_names.values()).index(active_id) if active_id in dash_names.values() else 0
        )
        sel_name = st.selectbox(
            "Open dashboard", list(dash_names.keys()), index=default_idx, key="dash_open_select"
        )
        sel_id = dash_names[sel_name]
        st.session_state["active_dash"] = sel_id

        dash = get_dashboard(sel_id)
        if not dash:
            st.error("Failed to load dashboard")
        else:
            # Header meta
            st.markdown(f"#### {dash['name']}")
            if dash.get("description"):
                st.caption(dash["description"])
            meta_cols = st.columns([2, 2, 3])
            meta_cols[0].caption(f"ID: {dash['id']} · {len(dash.get('widgets',[]))} widgets")
            meta_cols[1].caption(f"Created: {dash.get('created_at','')[:16]}")
            # Badges
            is_public = dash.get("is_public", False)
            slug = dash.get("share_slug")
            if is_public and slug:
                meta_cols[2].markdown(
                    f'<span class="fresh-badge">public</span> <span class="share-box">/api/dashboards/share/{slug}</span>',
                    unsafe_allow_html=True,
                )

            # Actions row
            a1, a2, a3, a4, a5 = st.columns(5)
            with a1:
                if st.button("🔗 Share / Copy link", key=f"share_{sel_id}"):
                    if is_public and slug:
                        share_url = f"{BACKEND_URL}/api/dashboards/share/{slug}"
                        frontend_url = f"?share={slug}"
                        st.success(f"Shared: {share_url}")
                        st.code(frontend_url, language="text")
                        st.caption("Frontend share link uses ?share=slug")
                    else:
                        r = requests.post(f"{BACKEND_URL}/api/dashboards/{sel_id}/share", timeout=5)
                        if r.status_code == 200:
                            sj = r.json()
                            st.success(f"Shared: {sj['url']} (slug {sj['slug']})")
                            st.toast("Link created", icon="🔗")
                            st.rerun()
                        else:
                            st.error(f"Share failed: {r.text[:400]}")
            with a2:
                if st.button("🚫 Unshare", key=f"unshare_{sel_id}"):
                    r = requests.post(f"{BACKEND_URL}/api/dashboards/{sel_id}/unshare", timeout=5)
                    if r.status_code == 200:
                        st.toast("Unshared", icon="✅")
                        st.rerun()
                    else:
                        st.error(r.text[:300])
            with a3:
                if st.button("📋 Duplicate", key=f"dup_{sel_id}"):
                    r = requests.post(
                        f"{BACKEND_URL}/api/dashboards/{sel_id}/duplicate", timeout=10
                    )
                    if r.status_code == 200:
                        st.session_state["active_dash"] = r.json()["id"]
                        st.toast("Duplicated", icon="📋")
                        st.rerun()
                    else:
                        st.error(f"Duplicate failed: {r.text[:400]}")
            with a4:
                dl_json_url = f"{BACKEND_URL}/api/dashboards/{sel_id}/export?format=json"
                st.link_button("⬇️ JSON", dl_json_url)
            with a5:
                dl_zip_url = f"{BACKEND_URL}/api/dashboards/{sel_id}/export?format=csv"
                st.link_button("⬇️ CSV Zip", dl_zip_url)

            if is_public and slug:
                with st.expander("Embed & share"):
                    st.code(
                        f'<iframe src="{BACKEND_URL}/api/dashboards/share/{slug}" width="100%" height="600" style="border:1px solid #e2e8f0; border-radius:8px;"></iframe>',
                        language="html",
                    )
                    st.caption(
                        "Frontend share (Streamlit): append `?share=<slug>` to your frontend URL"
                    )

            st.divider()

            # Version for staleness
            try:
                r_v = requests.get(f"{BACKEND_URL}/api/datasets/{dataset_id}/versions", timeout=5)
                current_version = (
                    r_v.json().get("current_version", 0) if r_v.status_code == 200 else 0
                )
            except:
                current_version = 0

            widgets = dash.get("widgets", [])
            if not widgets:
                st.info(
                    "No widgets yet — go to **Chat** and click **📌 Pin to Dashboard** on any result."
                )
            else:
                # Apply client-side filter to table view (not to chart — chart is snapshot, refresh re-runs)
                def _filtered_df_for_widget(w):
                    res = w.get("result")
                    if not res or not res.get("data") or not res.get("columns"):
                        return None
                    try:
                        data = res["data"]
                        # data may be list of dicts or list of lists
                        if data and isinstance(data[0], dict):
                            df = pd.DataFrame(data)
                        else:
                            df = pd.DataFrame(data, columns=res["columns"])
                        if f_col != "(none)" and f_vals and f_col in df.columns:
                            df = df[df[f_col].isin(f_vals)]
                        return df
                    except Exception:
                        return None

                # Grid 2-col
                for i in range(0, len(widgets), 2):
                    cols = st.columns(2)
                    for j, col in enumerate(cols):
                        idx = i + j
                        if idx >= len(widgets):
                            continue
                        w = widgets[idx]
                        is_stale = w.get("dataset_version", 0) != current_version
                        badge = (
                            '<span class="stale-badge">stale — refresh</span>'
                            if is_stale
                            else '<span class="fresh-badge">fresh</span>'
                        )
                        with col:
                            with st.container(border=True):
                                st.markdown(
                                    f'<div class="widget-title">{w.get("title","Untitled")} {badge}</div>',
                                    unsafe_allow_html=True,
                                )
                                st.markdown(
                                    f'<div class="widget-caption">{w.get("query","")[:120]}</div>',
                                    unsafe_allow_html=True,
                                )
                                # Table (filtered client-side)
                                df_f = _filtered_df_for_widget(w)
                                if df_f is not None:
                                    st.dataframe(
                                        df_f.head(30), use_container_width=True, height=220
                                    )
                                    st.caption(
                                        f"{len(df_f)} rows (filtered)"
                                        if f_col != "(none)"
                                        else f"{w.get('result',{}).get('rows', len(df_f))} rows"
                                    )
                                elif w.get("result"):
                                    st.json(w["result"])
                                # Chart
                                if w.get("chart"):
                                    try:
                                        fig = go.Figure(w["chart"])
                                        fig.update_layout(
                                            height=260,
                                            margin=dict(l=10, r=10, t=28, b=10),
                                            font=dict(family="Inter", size=11),
                                            paper_bgcolor="white",
                                            plot_bgcolor="white",
                                        )
                                        st.plotly_chart(
                                            fig,
                                            use_container_width=True,
                                            config={"displayModeBar": False},
                                        )
                                    except Exception as e:
                                        st.error(f"Chart error: {e}")
                                        st.json(w["chart"])
                                # Code caption
                                if w.get("code"):
                                    with st.expander("code"):
                                        st.code(w["code"], language="python")
                                b1, b2 = st.columns(2)
                                with b1:
                                    if st.button("🔄 Refresh", key=f"refresh_{w['id']}_{sel_id}"):
                                        with st.spinner("Refreshing..."):
                                            r = requests.post(
                                                f"{BACKEND_URL}/api/dashboards/{sel_id}/widgets/{w['id']}/refresh",
                                                timeout=30,
                                            )
                                            if r.status_code == 200:
                                                st.toast("Refreshed", icon="✅")
                                                st.rerun()
                                            else:
                                                st.error(f"Refresh failed: {r.text[:500]}")
                                with b2:
                                    if st.button("🗑️ Remove", key=f"remove_{w['id']}_{sel_id}"):
                                        r = requests.delete(
                                            f"{BACKEND_URL}/api/dashboards/{sel_id}/widgets/{w['id']}",
                                            headers=_auth_headers(),
                                            timeout=5,
                                        )
                                        if r.status_code == 200:
                                            st.toast("Removed", icon="🗑️")
                                            st.rerun()
                                        else:
                                            st.error(r.text[:300])
                                st.caption(
                                    f"pinned {w.get('created_at','')[:16]} · code version v{w.get('dataset_version',0)} · current v{current_version}"
                                )
                                # Inline comments per widget — threaded via dashboard comments (filter by widget mentions)
                                with st.expander(f"💬 Comments ({len(dash.get('comments',[]))})"):
                                    try:
                                        _cmts = dash.get("comments", [])
                                        # Show last 3 comments mentioning this widget's title or id
                                        for cm in _cmts[-4:]:
                                            st.markdown(
                                                f"**{cm.get('user','anon')}** · {cm.get('created_at','')[:16]}"
                                            )
                                            st.caption(cm.get("text", "")[:160])
                                        _cmt_text = st.text_input(
                                            "Comment",
                                            placeholder="Check this metric…",
                                            key=f"cmt_{w['id']}_{sel_id}",
                                            label_visibility="collapsed",
                                        )
                                        if st.button("Post", key=f"cmt_post_{w['id']}_{sel_id}"):
                                            if _cmt_text.strip():
                                                try:
                                                    rr = requests.post(
                                                        f"{BACKEND_URL}/api/dashboards/{sel_id}/comments",
                                                        json={
                                                            "text": f"[{w.get('title','')}]: {_cmt_text.strip()}",
                                                            "user": (_current_user() or {}).get(
                                                                "email", "anon"
                                                            ),
                                                        },
                                                        headers=_auth_headers(),
                                                        timeout=5,
                                                    )
                                                    if rr.status_code == 201:
                                                        st.toast("Comment posted", icon="💬")
                                                        st.rerun()
                                                    else:
                                                        st.error(rr.text[:300])
                                                except Exception as e:
                                                    st.error(str(e))
                                            else:
                                                st.toast("Empty", icon="⚠️")
                                        # Link to full comments tab
                                        st.caption(f"View all {len(_cmts)} in Schedules → Comments")
                                    except Exception:
                                        pass

            st.divider()
            # Dashboard-level comments
            with st.expander(f"💬 All comments ({len(dash.get('comments',[]))})"):
                try:
                    _all_c = dash.get("comments", [])
                    if not _all_c:
                        st.caption("No comments yet — add one above per widget or here.")
                    for cm in _all_c:
                        st.markdown(
                            f"**{cm.get('user','anon')}** · {cm.get('created_at','')[:16]} {('↳ '+cm.get('parent_id','') if cm.get('parent_id') else '')}"
                        )
                        st.caption(cm.get("text", ""))
                        st.divider()
                    _acmt = st.text_input(
                        "New comment (dashboard)",
                        placeholder="Great dashboard!",
                        key=f"dash_cmt_{sel_id}",
                        label_visibility="collapsed",
                    )
                    if st.button("Post dashboard comment", key=f"dash_cmt_btn_{sel_id}"):
                        if _acmt.strip():
                            rr = requests.post(
                                f"{BACKEND_URL}/api/dashboards/{sel_id}/comments",
                                json={
                                    "text": _acmt.strip(),
                                    "user": (_current_user() or {}).get("email", "anon"),
                                },
                                headers=_auth_headers(),
                                timeout=5,
                            )
                            if rr.status_code == 201:
                                st.toast("Posted", icon="💬")
                                st.rerun()
                except Exception:
                    st.caption("Comments unavailable")
            with st.expander("⚙️ Danger zone"):
                cda, cdb = st.columns(2)
                with cda:
                    if st.button("🗑️ Delete dashboard", key=f"del_dash_{sel_id}", type="primary"):
                        r = requests.delete(
                            f"{BACKEND_URL}/api/dashboards/{sel_id}",
                            headers=_auth_headers(),
                            timeout=5,
                        )
                        if r.status_code == 200:
                            st.session_state["active_dash"] = None
                            st.toast("Deleted", icon="🗑️")
                            st.rerun()
                        else:
                            st.error(r.text[:300])

with tabs[6]:
    st.subheader("Connect — Live Data & Joins")
    st.caption(
        "Add Postgres, MySQL, SQLite, BigQuery, or Google Sheets as a **live virtual dataset**. Then chat with SELECT or join files. OSS stores DSN plain — use env for prod (encrypted in L7)."
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        with st.container(border=True):
            st.markdown("**➕ New connector**")
            kind = st.selectbox(
                "Kind", ["postgres", "mysql", "sqlite", "bigquery", "sheets"], key="conn_kind"
            )
            name = st.text_input(
                "Name", placeholder="e.g., Prod Postgres or My Sheet", key="conn_name"
            )
            dsn = ""
            table = ""
            sheet_url = ""
            creds = ""
            if kind in ("postgres", "mysql"):
                dsn = st.text_input(
                    "DSN",
                    placeholder=(
                        "postgresql://user:pass@host:5432/db"
                        if kind == "postgres"
                        else "mysql://user:pass@host:3306/db"
                    ),
                    key="conn_dsn",
                    type="password",
                )
                table = st.text_input(
                    "Table (optional if you will query SQL)",
                    placeholder="public.sales",
                    key="conn_table",
                )
                st.caption(
                    "⚠️ DSN stored plain in OSS. For prod, use env var — encrypted storage in L7."
                )
            elif kind == "sqlite":
                dsn = st.text_input(
                    "SQLite path",
                    value=":memory:",
                    placeholder=":memory: or /data/db.sqlite",
                    key="conn_sqlite_path",
                )
                table = st.text_input("Table", placeholder="sales", key="conn_sqlite_table")
                st.caption(
                    "Demo: use `:memory:` — but for persistence use a file. CI demo loads sample CSV into sqlite."
                )
                if st.button("📥 Load sample_data into SQLite (demo)", key="conn_demo_sqlite"):
                    try:
                        import sqlite3, pandas as _pd, pathlib as _pl

                        _db = dsn if dsn and dsn != ":memory:" else "/tmp/demo_connect.sqlite"
                        _con = sqlite3.connect(_db)
                        for _csv in ["sample_data/sales.csv", "sample_data/employees.csv"]:
                            _p = _pl.Path(_csv)
                            if _p.exists():
                                _df = _pd.read_csv(_p)
                                _tbl = _p.stem
                                _df.to_sql(_tbl, _con, if_exists="replace", index=False)
                        _con.close()
                        st.success(
                            f"Loaded samples into {_db}. Now create connectors with dsn={_db} table=sales or employees"
                        )
                    except Exception as e:
                        st.error(str(e))
            elif kind == "sheets":
                sheet_url = st.text_input(
                    "Google Sheets share link",
                    placeholder="https://docs.google.com/spreadsheets/d/<ID>/edit",
                    key="conn_sheet_url",
                )
                st.caption(
                    "Sheet must be **Anyone with link — Viewer**. Private sheets need OAuth (L7). Fetched via export CSV, cached 60s."
                )
            elif kind == "bigquery":
                table = st.text_input(
                    "Table", placeholder="project.dataset.table", key="conn_bq_table"
                )
                creds = st.text_area(
                    "Service JSON (or set GOOGLE_APPLICATION_CREDENTIALS env)",
                    placeholder='{"type":"service_account",...}',
                    key="conn_bq_creds",
                    height=80,
                )
                if not creds:
                    st.caption(
                        "Requires `pandas-gbq` + `google-cloud-bigquery` — not installed in OSS demo, returns 501 with message."
                    )
            if st.button("Create connector", type="primary", key="conn_create"):
                if not name.strip():
                    st.toast("Name required", icon="⚠️")
                else:
                    payload = {"kind": kind, "name": name.strip()}
                    if dsn:
                        payload["dsn"] = dsn
                    if table:
                        payload["table"] = table
                    if sheet_url:
                        payload["sheet_url"] = sheet_url
                    if creds:
                        payload["credentials_json"] = creds
                    try:
                        r = requests.post(f"{BACKEND_URL}/api/connectors", json=payload, timeout=15)
                        if r.status_code == 201:
                            j = r.json()
                            st.success(
                                f"Connected: {j.get('id')} — {j.get('column_names')} · {j.get('rows')} rows"
                            )
                            st.toast("Connector created", icon="🔌")
                            if j.get("sample_error"):
                                st.warning(f"Sample fetch warning: {j['sample_error'][:300]}")
                            st.rerun()
                        else:
                            st.error(f"Create failed ({r.status_code}): {r.text[:600]}")
                    except Exception as e:
                        st.error(str(e))
    with c2:
        with st.container(border=True):
            st.markdown("**🔌 Live query (read-only)**")
            st.caption(
                "All queries are read-only — INSERT/UPDATE/DROP blocked. Uses DuckDB validation."
            )
            # List connectors for query
            try:
                _list_r = requests.get(f"{BACKEND_URL}/api/connectors", timeout=5)
                _conn_list = _list_r.json() if _list_r.status_code == 200 else []
            except:
                _conn_list = []
            if not _conn_list:
                st.info("No connectors yet. Create one on the left.")
            else:
                q_conn_names = {
                    f"{c['name']} ({c['kind']}) • {c['id'][:6]}": c["id"] for c in _conn_list
                }
                q_sel = st.selectbox("Connector", list(q_conn_names.keys()), key="conn_q_sel")
                q_cid = q_conn_names[q_sel]
                sql = st.text_area(
                    "SQL (SELECT / WITH only)",
                    value="SELECT * FROM df LIMIT 5",
                    height=100,
                    key="conn_sql",
                )
                q_limit = st.slider("Limit", 1, 500, 50, key="conn_limit")
                col_test, col_run = st.columns(2)
                with col_test:
                    if st.button("Test connection", key="conn_test_btn"):
                        try:
                            r = requests.post(
                                f"{BACKEND_URL}/api/connectors/{q_cid}/test", timeout=10
                            )
                            if r.status_code == 200:
                                st.success(f"OK: {r.json()}")
                            else:
                                st.error(r.text[:500])
                        except Exception as e:
                            st.error(str(e))
                with col_run:
                    if st.button("Run query", type="primary", key="conn_run"):
                        try:
                            r = requests.post(
                                f"{BACKEND_URL}/api/connectors/{q_cid}/query",
                                json={"sql": sql, "limit": q_limit},
                                timeout=15,
                            )
                            if r.status_code == 200:
                                j = r.json()
                                st.success(f"{j.get('rows')} rows")
                                # Show preview
                                try:
                                    _df = pd.DataFrame(j["preview"]["data"])
                                    st.dataframe(_df, use_container_width=True)
                                    # Simple chart
                                    if len(_df.columns) >= 2:
                                        try:
                                            fig = px.bar(
                                                _df.head(20),
                                                x=_df.columns[0],
                                                y=_df.columns[1],
                                                title="Query preview",
                                            )
                                            st.plotly_chart(fig, use_container_width=True)
                                        except:
                                            pass
                                except:
                                    st.json(j["preview"])
                                st.json({k: j[k] for k in ("rows", "columns") if k in j})
                            elif r.status_code == 400:
                                st.error(f"Blocked: {r.json().get('detail', r.text)[:500]}")
                            elif r.status_code == 501:
                                st.warning(r.json().get("detail", r.text)[:600])
                            else:
                                st.error(r.text[:600])
                        except Exception as e:
                            st.error(str(e))

    st.divider()
    with st.container(border=True):
        st.markdown("**🔗 Join datasets (federation)**")
        st.caption(
            "Select 2–3 file datasets (or connectors) → join on a common column via DuckDB. Creates a new dataset with lineage badge. Then chat or dashboard from the joined data."
        )
        # Build options from datasets (exclude connectors that failed? include all)
        if not datasets:
            st.info("No datasets to join")
        else:
            # Filter file + connector that have data
            _join_opts = {
                f"{d['original_filename']} ({d['rows']} rows) • {d['id'][:6]}": d["id"]
                for d in datasets
            }
            sel_ids = st.multiselect(
                "Pick 2–3 datasets", list(_join_opts.keys()), max_selections=3, key="join_sel"
            )
            # Find common columns
            common = set()
            if len(sel_ids) >= 2:
                ids = [_join_opts[k] for k in sel_ids]
                metas = [next((x for x in datasets if x["id"] == iid), {}) for iid in ids]
                cols_list = [set(m.get("column_names", [])) for m in metas]
                common = set.intersection(*cols_list) if cols_list else set()
                if common:
                    on = st.selectbox("Join on", sorted(common), key="join_on")
                else:
                    st.warning(
                        f"No common columns between {sel_ids}. Pick datasets that share a key (e.g., Region, Date)."
                    )
                    on = st.text_input("Join on (manual)", key="join_on_manual")
                how = st.selectbox(
                    "How", ["left", "inner", "right", "outer"], index=0, key="join_how"
                )
                if st.button("Join → create new dataset", type="primary", key="join_btn"):
                    if len(ids) < 2:
                        st.toast("Pick at least 2", icon="⚠️")
                    elif not on or not on.strip():
                        st.toast("Join key required", icon="⚠️")
                    else:
                        try:
                            r = requests.post(
                                f"{BACKEND_URL}/api/datasets/join",
                                json={"ids": ids, "on": on.strip(), "how": how},
                                timeout=20,
                            )
                            if r.status_code == 200:
                                j = r.json()
                                st.success(
                                    f"Joined → {j['id']}: {j['rows']} rows, lineage {j.get('lineage')} — select it above to chat"
                                )
                                st.toast("Join created", icon="🔗")
                                st.rerun()
                            else:
                                st.error(f"Join failed ({r.status_code}): {r.text[:800]}")
                        except Exception as e:
                            st.error(str(e))
            else:
                st.caption("Select 2–3 datasets to see common join keys")

    st.divider()
    st.caption(
        "💡 **NL→SQL**: When a live connector is selected above, Chat treats English as SQL. With a key (Groq/OpenAI) it translates via LLM; without a key it falls back to heuristic groupby + tip: *Add GROQ_API_KEY for full NL→SQL or type SELECT.*"
    )

with tabs[7]:
    st.subheader("Analytics — Why, Outliers, Segments & Forecast")
    st.caption(
        "One-click deep dives. All use read-only `df` via safe sandbox; forecast works even on 24 rows (naive fallback if `statsforecast` missing)."
    )

    a1, a2, a3, a4 = st.columns(4)
    with a1:
        if st.button("🔍 Explain drop", use_container_width=True, key="an_why"):
            st.session_state["pending_query"] = "Why did sales drop in March?"
            st.toast("Prefilled: Why did sales drop in March?", icon="🔍")
        if st.button("📉 Why increase?", use_container_width=True, key="an_why_inc"):
            st.session_state["pending_query"] = "Why did sales increase in June?"
            st.toast("Prefilled", icon="📈")
    with a2:
        # Outliers
        _out_opts = profile.get("numeric_columns") or profile.get("column_names") or ["Sales"]
        _out_opts = [o for o in _out_opts if o][:3] or ["Sales"]
        ocol = st.selectbox("Outlier col", _out_opts, key="an_out_col")
        omethod = st.selectbox("Method", ["iqr", "zscore"], key="an_out_method")
        if st.button("🚨 Outliers", use_container_width=True, key="an_out_btn"):
            st.session_state["pending_query"] = f"Show outliers in {ocol} via {omethod}"
            st.toast(f"Prefilled: outliers in {ocol}", icon="🚨")
        if st.button("Correlation heatmap", use_container_width=True, key="an_corr"):
            st.session_state["pending_query"] = "correlation heatmap"
            st.toast("Prefilled: correlation heatmap", icon="🔗")
    with a3:
        _seg_by_opts = (
            profile.get("categorical_columns") or profile.get("column_names") or ["(none)"]
        )
        _seg_by_opts = [o for o in _seg_by_opts if o][:4] or ["(none)"]
        by_col = st.selectbox("Segment by", _seg_by_opts, key="an_seg_by")
        _seg_met_opts = profile.get("numeric_columns") or profile.get("column_names") or ["Sales"]
        _seg_met_opts = [o for o in _seg_met_opts if o][:4] or ["Sales"]
        metric = st.selectbox("Metric", _seg_met_opts, key="an_seg_metric")
        agg = st.selectbox("Agg", ["sum", "mean", "median", "count"], key="an_seg_agg")
        if st.button("🧩 Segment", use_container_width=True, key="an_seg_btn"):
            st.session_state["pending_query"] = f"segment by {by_col}"
            st.toast(f"Prefilled: segment by {by_col}", icon="🧩")
        if st.button("Treemap", use_container_width=True, key="an_seg_treemap"):
            st.session_state["pending_query"] = f"segment by {by_col}"
            st.toast("Prefilled", icon="🧩")
    with a4:
        f_periods = st.slider("Forecast periods", 1, 12, 3, key="an_fc_periods")
        f_freq = st.selectbox("Freq", ["M", "W", "D"], index=0, key="an_fc_freq")
        _fc_opts = profile.get("numeric_columns") or profile.get("column_names") or ["Sales"]
        _fc_opts = [o for o in _fc_opts if o] or ["Sales"]
        f_metric = st.selectbox("Forecast metric", _fc_opts, key="an_fc_metric")
        if st.button("🔮 Forecast", use_container_width=True, key="an_fc_btn"):
            st.session_state["pending_query"] = f"forecast {f_metric} for next {f_periods} months"
            if f_freq == "W":
                st.session_state["pending_query"] = (
                    f"forecast {f_metric} for next {f_periods} weeks"
                )
            elif f_freq == "D":
                st.session_state["pending_query"] = f"forecast {f_metric} for next {f_periods} days"
            st.toast("Prefilled: forecast", icon="🔮")

    st.divider()
    with st.container(border=True):
        st.markdown("**🧪 What-if simulator**")
        _w_opts = profile.get("numeric_columns") or profile.get("column_names") or ["Sales"]
        _w_opts = [o for o in _w_opts if o] or ["Sales"]
        w_col = st.selectbox("Column", _w_opts, key="an_w_col")
        w_pct = st.slider("Change %", -50, 100, 10, key="an_w_pct")
        w_by = st.selectbox(
            "Group by (optional)",
            ["(none)"] + (profile.get("categorical_columns", []) or []),
            key="an_w_by",
        )
        if st.button("Run what-if", key="an_w_btn"):
            by_part = f" by {w_by}" if w_by != "(none)" else ""
            st.session_state["pending_query"] = f"what if {w_col} increased {w_pct}%{by_part}"
            st.toast(f"What-if {w_col} {w_pct:+}%", icon="🧪")

    st.caption(
        "Tip: Run in **Chat** tab — results show table + chart. Pin any analytics result to Dashboards. Forecast shows band + MAE/RMSE when ≥20 history points."
    )

with tabs[8]:
    st.subheader("Schedules & Automation")
    st.caption(
        "Schedule a dashboard as PDF to email/Slack on cron. Threshold alerts fire when metric drops >10%. Reports bundle widgets + markdown. Comments live on dashboards. Slack bot answers via `/insight`."
    )
    col_s1, col_s2 = st.columns([1, 1])
    with col_s1:
        with st.container(border=True):
            st.markdown("**➕ New schedule**")
            # Pick dashboard
            try:
                _all_d = (
                    requests.get(f"{BACKEND_URL}/api/datasets", timeout=3).json()
                    if datasets
                    else []
                )
            except:
                _all_d = []
            # Dashboard picker from current dataset's dashboards + all
            dash_opts = {}
            for d in _dashes_all:
                dash_opts[f"{d['name']} • {d['id'][:6]}"] = d["id"]
            # Also allow query-based schedule
            sched_dash = st.selectbox(
                "Dashboard (or leave blank for query)",
                ["(query)"] + list(dash_opts.keys()),
                key="sched_dash",
            )
            if sched_dash == "(query)":
                q = st.text_input("Query", placeholder="Show top 5 products", key="sched_q")
                if not _all_d:
                    st.warning("No dataset — upload first")
                # dataset_id needed for query; use current dataset_id
            sched_name = st.text_input("Name", placeholder="Weekly Sales digest", key="sched_name")
            # Cron helper
            cron = st.text_input(
                "Cron", value="0 9 * * 1", placeholder="0 9 * * 1 (Mon 9am)", key="sched_cron"
            )
            # Presets
            c_presets = st.columns(4)
            if c_presets[0].button("Daily 9am", key="cron_daily"):
                st.session_state["sched_cron"] = "0 9 * * *"
                st.rerun()
            if c_presets[1].button("Mon 9am", key="cron_mon"):
                st.session_state["sched_cron"] = "0 9 * * 1"
                st.rerun()
            if c_presets[2].button("Hourly", key="cron_hourly"):
                st.session_state["sched_cron"] = "0 * * * *"
                st.rerun()
            if c_presets[3].button("Every 5m", key="cron_5m"):
                st.session_state["sched_cron"] = "*/5 * * * *"
                st.rerun()
            st.caption(
                "Cron: `m h dom mon dow` — 0 9 * * 1 = Mon 9am. Use `0 9 * * *` for daily 9am."
            )
            channel = st.selectbox("Channel", ["email", "slack", "both"], key="sched_channel")
            to_addr = st.text_input(
                "To",
                placeholder=(
                    "you@example.com or https://hooks.slack.com/..."
                    if channel == "email"
                    else "Slack webhook URL"
                ),
                key="sched_to",
            )
            # Threshold optional
            with st.expander("Threshold alert (optional)"):
                thr_enabled = st.checkbox("Enable threshold", key="thr_enabled")
                thr_pct = st.slider("Drop % to alert", 5, 50, 10, key="thr_pct")
                thr_dir = st.selectbox("Direction", ["drop", "increase"], key="thr_dir")
                thr_metric = st.text_input(
                    "Metric keyword (for future)", placeholder="Sales", key="thr_metric"
                )
            if st.button("Create schedule", type="primary", key="sched_create"):
                if not sched_name.strip():
                    st.toast("Name required", icon="⚠️")
                elif not cron.strip() or len(cron.split()) != 5:
                    st.toast("Cron must be 5 fields", icon="⚠️")
                elif not to_addr.strip():
                    st.toast("To required", icon="⚠️")
                else:
                    payload = {
                        "name": sched_name.strip(),
                        "cron": cron.strip(),
                        "channel": channel,
                        "to": to_addr.strip(),
                    }
                    if sched_dash != "(query)":
                        payload["dashboard_id"] = dash_opts[sched_dash]
                    else:
                        if not q or not q.strip():
                            st.toast("Query required for query schedule", icon="⚠️")
                            st.stop()
                        payload["query"] = q.strip()
                        payload["dataset_id"] = dataset_id
                    if thr_enabled:
                        payload["threshold"] = {
                            "pct": thr_pct,
                            "direction": thr_dir,
                            "metric": thr_metric,
                        }
                    try:
                        r = requests.post(f"{BACKEND_URL}/api/schedules", json=payload, timeout=10)
                        if r.status_code == 201:
                            st.success(f"Schedule {r.json()['id']} created — next via cron {cron}")
                            st.toast("Schedule created", icon="⏰")
                            st.rerun()
                        else:
                            st.error(f"Create failed ({r.status_code}): {r.text[:600]}")
                    except Exception as e:
                        st.error(str(e))
    with col_s2:
        with st.container(border=True):
            st.markdown("**📋 Existing schedules**")
            try:
                rss = requests.get(f"{BACKEND_URL}/api/schedules", timeout=5)
                scheds = rss.json() if rss.status_code == 200 else []
            except:
                scheds = []
            if not scheds:
                st.info("No schedules yet — create on the left.")
            else:
                for s in scheds:
                    with st.container(border=True):
                        st.markdown(
                            f"**{s.get('name','')}** • `{s.get('cron')}` • {s.get('channel')} → `{s.get('to','')[:28]}`"
                        )
                        st.caption(
                            f"ID {s['id']} • dashboard {s.get('dashboard_id') or s.get('query','')[:24]} • enabled {s.get('enabled')}"
                        )
                        last = s.get("last_run", "")[:16] if s.get("last_run") else "never"
                        runs = s.get("runs", [])
                        status = runs[0].get("status", "") if runs else "—"
                        st.caption(f"Last: {last} • {status} • {len(runs)} runs")
                        if s.get("threshold"):
                            st.caption(f"Threshold: {s['threshold']}")
                        b1, b2, b3 = st.columns(3)
                        with b1:
                            if st.button("Run now", key=f"sched_run_{s['id']}"):
                                with st.spinner("Running..."):
                                    try:
                                        rr = requests.post(
                                            f"{BACKEND_URL}/api/schedules/{s['id']}/run", timeout=30
                                        )
                                        if rr.status_code == 200:
                                            st.success(
                                                f"Ran: {rr.json().get('status')} — {rr.json().get('detail','')[:120]}"
                                            )
                                            st.toast("Ran", icon="✅")
                                            st.rerun()
                                        else:
                                            st.error(rr.text[:600])
                                    except Exception as e:
                                        st.error(str(e))
                        with b2:
                            pdf_url = f"{BACKEND_URL}/api/schedules/{s['id']}/export"
                            st.link_button("PDF", pdf_url)
                        with b3:
                            if st.button("Delete", key=f"sched_del_{s['id']}"):
                                try:
                                    rr = requests.delete(
                                        f"{BACKEND_URL}/api/schedules/{s['id']}",
                                        headers=_auth_headers(),
                                        timeout=5,
                                    )
                                    if rr.status_code == 200:
                                        st.toast("Deleted", icon="🗑️")
                                        st.rerun()
                                    else:
                                        st.error(rr.text[:300])
                                except Exception as e:
                                    st.error(str(e))
                        with st.expander("Runs"):
                            st.json(s.get("runs", []))
    st.divider()
    with st.container(border=True):
        st.markdown("**📄 Report Builder**")
        st.caption("Bundle dashboard widgets + markdown into a PDF report.")
        # Pick dashboard
        rep_dash_sel = st.selectbox(
            "Dashboard",
            list(dash_opts.keys()) if dash_opts else ["(no dashboards)"],
            key="rep_dash_sel",
        )
        rep_dash_id = dash_opts.get(rep_dash_sel) if dash_opts else None
        rep_name = st.text_input("Report name", placeholder="QBR Sales Deck", key="rep_name")
        rep_desc = st.text_input("Description", placeholder="Quarterly review", key="rep_desc")
        # Widget picker if dashboard selected
        if rep_dash_id:
            try:
                _rep_dash = requests.get(
                    f"{BACKEND_URL}/api/dashboards/{rep_dash_id}", timeout=5
                ).json()
                _widgets = _rep_dash.get("widgets", [])
            except:
                _widgets = []
            if _widgets:
                opts = {f"{w.get('title','Widget')} • {w.get('id')[:4]}": w["id"] for w in _widgets}
                sel_wids = st.multiselect("Widgets", list(opts.keys()), key="rep_wids")
                md = st.text_area(
                    "Markdown block (optional)",
                    placeholder="# Executive summary\n- Insight 1\n- Forecast shows +12% next quarter",
                    height=100,
                    key="rep_md",
                )
                if st.button("Create report", type="primary", key="rep_create"):
                    if not rep_name.strip():
                        st.toast("Name required", icon="⚠️")
                    else:
                        blocks = []
                        if md and md.strip():
                            blocks.append({"type": "markdown", "text": md.strip()})
                        for k in sel_wids:
                            blocks.append({"type": "widget", "widget_id": opts[k]})
                        if not blocks:
                            st.toast("Add at least one widget or markdown", icon="⚠️")
                        else:
                            try:
                                r = requests.post(
                                    f"{BACKEND_URL}/api/reports",
                                    json={
                                        "dashboard_id": rep_dash_id,
                                        "name": rep_name.strip(),
                                        "description": rep_desc.strip(),
                                        "blocks": blocks,
                                    },
                                    timeout=10,
                                )
                                if r.status_code == 201:
                                    st.success(f"Report {r.json()['id']} created")
                                    st.toast("Report created", icon="📄")
                                else:
                                    st.error(f"Create failed: {r.text[:600]}")
                            except Exception as e:
                                st.error(str(e))
            else:
                st.info("Dashboard has no widgets — add via Chat → Pin first.")
        # List reports
        try:
            rr = requests.get(f"{BACKEND_URL}/api/reports", timeout=5)
            reps = rr.json() if rr.status_code == 200 else []
        except:
            reps = []
        if reps:
            st.markdown("**Existing reports**")
            for rep in reps[:8]:
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1:
                    st.caption(
                        f"📄 **{rep.get('name')}** • {rep['id'][:6]} • {len(rep.get('blocks',[]))} blocks • {rep.get('dashboard_id','')[:6]}"
                    )
                with c2:
                    pdf_url = f"{BACKEND_URL}/api/reports/{rep['id']}/export?format=pdf"
                    st.link_button("PDF", pdf_url)
                with c3:
                    if st.button("Delete", key=f"rep_del_{rep['id']}"):
                        try:
                            rr = requests.delete(
                                f"{BACKEND_URL}/api/reports/{rep['id']}",
                                headers=_auth_headers(),
                                timeout=5,
                            )
                            if rr.status_code == 200:
                                st.toast("Deleted", icon="🗑️")
                                st.rerun()
                        except Exception as e:
                            st.error(str(e))
    st.divider()
    with st.container(border=True):
        st.markdown("**💬 Dashboard comments**")
        st.caption(
            "Comments live inline in `dashboards/{id}.json` — max 100 per dashboard. Threaded via parent_id (flat for OSS)."
        )
        if not _dashes_all:
            st.info("No dashboards — create one to comment.")
        else:
            c_dash = st.selectbox(
                "Dashboard for comments", [d["name"] for d in _dashes_all], key="cmt_dash_sel"
            )
            c_dash_id = next(
                (d["id"] for d in _dashes_all if d["name"] == c_dash), _dashes_all[0]["id"]
            )
            try:
                rc = requests.get(f"{BACKEND_URL}/api/dashboards/{c_dash_id}/comments", timeout=5)
                comments = rc.json() if rc.status_code == 200 else []
            except:
                comments = []
            for cm in comments[-20:]:
                st.markdown(f"**{cm.get('user','anon')}** • {cm.get('created_at','')[:16]}")
                st.caption(cm.get("text", ""))
                st.divider()
            c_user = st.text_input("Your name", value="anon", key="cmt_user")
            c_text = st.text_input(
                "New comment", placeholder="Check Region West — looks off", key="cmt_text"
            )
            c_parent = st.text_input(
                "Parent ID (optional for thread)", placeholder="", key="cmt_parent"
            )
            if st.button("Post comment", key="cmt_post"):
                if not c_text.strip():
                    st.toast("Text required", icon="⚠️")
                else:
                    try:
                        r = requests.post(
                            f"{BACKEND_URL}/api/dashboards/{c_dash_id}/comments",
                            json={
                                "text": c_text.strip(),
                                "user": c_user.strip() or "anon",
                                "parent_id": c_parent.strip() or None,
                            },
                            timeout=5,
                        )
                        if r.status_code == 201:
                            st.toast("Comment posted", icon="💬")
                            st.rerun()
                        else:
                            st.error(r.text[:500])
                    except Exception as e:
                        st.error(str(e))
            st.caption(
                "Delete via API `DELETE /api/dashboards/{id}/comments/{cid}` — UI delete shown in runs for now."
            )

if is_cloud:
    if len(tabs) > 9:
        with tabs[9]:
            st.subheader("Cloud — Workspace & Billing")
            try:
                ws_id = st.session_state.get("user", {}).get("workspace_id", "default")
                # Billing
                br = requests.get(
                    f"{BACKEND_URL}/api/cloud/billing", headers=_auth_headers(), timeout=5
                )
                if br.status_code == 200:
                    b = br.json()
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Plan", b.get("plan", "free"))
                    c2.metric(
                        "Datasets",
                        str(b.get("usage", {}).get("datasets", 0))
                        + "/"
                        + str(b.get("quotas", {}).get("datasets", 3)),
                    )
                    c3.metric(
                        "Queries/mo",
                        str(b.get("usage", {}).get("queries_this_month", 0))
                        + "/"
                        + str(b.get("quotas", {}).get("queries_per_month", 50)),
                    )
                    # Upgrade
                    if b.get("plan") == "free":
                        if st.button("Upgrade to Pro ($19/mo)"):
                            rr = requests.post(
                                f"{BACKEND_URL}/api/cloud/billing/checkout",
                                json={"plan": "pro"},
                                headers=_auth_headers(),
                                timeout=10,
                            )
                            if rr.status_code == 200:
                                st.link_button("Checkout", rr.json().get("url", ""))
                                st.info("Mock checkout — pro will be active after webhook")
                            else:
                                st.error(rr.text[:300])
                else:
                    st.caption(f"Billing: {br.status_code}")
                st.divider()
                st.markdown("**Workspace Branding (enterprise)**")
                with st.form("brand_form"):
                    appn = st.text_input("App name", value="InsightAgent")
                    logo = st.text_input("Logo URL")
                    color = st.color_picker("Primary color", "#0f172a")
                    if st.form_submit_button("Save brand"):
                        rr = requests.post(
                            f"{BACKEND_URL}/api/cloud/workspaces/{ws_id}/brand",
                            json={"app_name": appn, "logo_url": logo, "primary_color": color},
                            headers=_auth_headers(),
                            timeout=5,
                        )
                        if rr.status_code == 200:
                            st.success("Branding saved")
                        else:
                            st.error(rr.text[:300])
                st.divider()
                st.markdown("**LLM — per workspace BYOK / Ollama**")
                try:
                    cur = requests.get(
                        f"{BACKEND_URL}/api/cloud/llm", headers=_auth_headers(), timeout=5
                    ).json()
                except:
                    cur = {}
                prov = st.selectbox(
                    "Provider",
                    ["auto", "openai", "groq", "gemini", "claude", "ollama", "heuristic"],
                    index=(
                        ["auto", "openai", "groq", "gemini", "claude", "ollama", "heuristic"].index(
                            cur.get("provider", "auto")
                        )
                        if cur.get("provider")
                        in ["auto", "openai", "groq", "gemini", "claude", "ollama", "heuristic"]
                        else 0
                    ),
                )
                model = st.text_input("Model", value=cur.get("model", ""))
                okey = st.text_input("OpenAI key (BYOK)", type="password", placeholder="sk-...")
                oll_url = st.text_input(
                    "Ollama URL", value=cur.get("ollama_url", "http://ollama:11434")
                )
                if st.button("Save LLM"):
                    rr = requests.post(
                        f"{BACKEND_URL}/api/cloud/llm",
                        json={
                            "provider": prov,
                            "model": model,
                            "openai_key": okey,
                            "ollama_url": oll_url,
                        },
                        headers=_auth_headers(),
                        timeout=8,
                    )
                    if rr.status_code == 200:
                        st.success(f"LLM set to {prov}")
                    else:
                        st.error(rr.text[:300])
                if st.button("Test Ollama"):
                    rr = requests.post(
                        f"{BACKEND_URL}/api/cloud/llm/test", headers=_auth_headers(), timeout=5
                    )
                    st.json(rr.json() if rr.status_code == 200 else {"err": rr.text[:200]})
            except Exception as e:
                st.error(str(e))
        with tabs[10]:
            st.subheader("Marketplace — Templates")
            try:
                lst = requests.get(
                    f"{BACKEND_URL}/api/marketplace", headers=_auth_headers(), timeout=5
                )
                if lst.status_code == 200:
                    for item in lst.json():
                        with st.container(border=True):
                            st.markdown(
                                "**" + item.get("name", "") + "** — " + item.get("description", "")
                            )
                            qs = ", ".join(item.get("queries", [])[:2])
                            st.caption("queries: " + qs)
                            if st.button(
                                "Install " + item.get("id", ""), key="mkt_" + item.get("id", "")
                            ):
                                rr = requests.post(
                                    BACKEND_URL
                                    + "/api/marketplace/"
                                    + item.get("id", "")
                                    + "/install",
                                    json={"dataset_id": dataset_id},
                                    headers=_auth_headers(),
                                    timeout=10,
                                )
                                if rr.status_code == 200:
                                    did = rr.json().get("dashboard", {}).get("id", "")[:6]
                                    st.success(
                                        "Installed " + item.get("id", "") + " — dashboard " + did
                                    )
                                    st.json(rr.json())
                                else:
                                    st.error(rr.text[:300])
                else:
                    st.error(lst.text[:300])
            except Exception as e:
                st.error(str(e))
# Version history (outside tabs for persistence)
st.divider()
# Version history moved: show under Analytics tab footer for transparency
with st.expander("📚 Version history (dataset lineage)"):
    try:
        r = requests.get(f"{BACKEND_URL}/api/datasets/{dataset_id}/versions", timeout=5)
        if r.status_code == 200:
            data = r.json()
            current = data.get("current_version", 0)
            versions = data.get("versions", [])
            st.caption(f"Current version: v{current} | Total: {len(versions)}")
            if versions:
                df_v = pd.DataFrame(versions)
                st.dataframe(df_v, use_container_width=True)
                v_options = [v["version"] for v in versions]
                sel_v = st.selectbox("Version", v_options, key="revert_select_bottom")
                if st.button("↩️ Revert", key="revert_btn_bottom"):
                    with st.spinner(f"Reverting to v{sel_v}..."):
                        try:
                            r2 = requests.post(
                                f"{BACKEND_URL}/api/datasets/{dataset_id}/revert",
                                json={"version": sel_v},
                                timeout=10,
                            )
                            if r2.status_code == 200:
                                st.success(f"✅ Reverted to v{sel_v}")
                                st.toast("↩️ Reverted", icon="✅")
                                st.rerun()
                            else:
                                st.error(f"Revert failed: {r2.text[:300]}")
                        except Exception as e:
                            st.error(f"Revert error: {str(e)}")
            else:
                st.info("No versions yet — v0 is original.")
        else:
            st.error(f"Failed to load versions: {r.text[:200]}")
    except Exception as e:
        st.error(f"Versions error: {str(e)}")

# Keep original version history block for backwards compat (hidden)
if False:
    st.subheader("📚 Version History")
    try:
        r = requests.get(f"{BACKEND_URL}/api/datasets/{dataset_id}/versions", timeout=5)
        if r.status_code == 200:
            data = r.json()
            current = data.get("current_version", 0)
            versions = data.get("versions", [])
            st.caption(f"Current version: v{current} | Total: {len(versions)}")
            if versions:
                df_v = pd.DataFrame(versions)
                st.dataframe(df_v, use_container_width=True)
                # Revert
                st.markdown("**Revert to version**")
                v_options = [v["version"] for v in versions]
                sel_v = st.selectbox("Version", v_options, key="revert_select")
                if st.button("↩️ Revert", key="revert_btn"):
                    with st.spinner(f"Reverting to v{sel_v}..."):
                        try:
                            r2 = requests.post(
                                f"{BACKEND_URL}/api/datasets/{dataset_id}/revert",
                                json={"version": sel_v},
                                timeout=10,
                            )
                            if r2.status_code == 200:
                                st.success(f"✅ Reverted to v{sel_v}")
                                st.toast("↩️ Reverted", icon="✅")
                                st.rerun()
                            else:
                                st.error(f"Revert failed: {r2.text[:300]}")
                        except Exception as e:
                            st.error(f"Revert error: {str(e)}")
            else:
                st.info("No versions yet — v0 is original.")
        else:
            st.error(f"Failed to load versions: {r.text[:200]}")
    except Exception as e:
        st.error(f"Versions error: {str(e)}")
