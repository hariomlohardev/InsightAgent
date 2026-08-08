from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Optional
import json, os
from pathlib import Path

from app.api.auth import get_current_user
from app.config import get_base_storage_path, get_storage_path, get_workspace_id
from app.core.storage import _atomic_write_json

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


def _marketplace_dir() -> Path:
    # Marketplace is global, not per-workspace
    p = get_base_storage_path() / "marketplace"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ensure_marketplace_seed():
    d = _marketplace_dir()
    # seed 10 templates if missing
    templates = [
        {
            "id": "market_research",
            "name": "Market Research",
            "description": "Segmentation + competitor queries",
            "queries": ["segment by Region", "top 5 Product by Sales", "correlation heatmap"],
            "dashboard_template": {"name": "Market Research Board", "widgets": []},
        },
        {
            "id": "invoice_parser",
            "name": "Invoice Parser",
            "description": "Extract totals, due dates",
            "queries": ["show outliers in Amount via iqr", "describe Amount"],
            "dashboard_template": {"name": "Invoices", "widgets": []},
        },
        {
            "id": "sales_forecast",
            "name": "Sales Forecast",
            "description": "Forecast next 3 months",
            "queries": ["forecast Sales for next 3 months"],
            "dashboard_template": {"name": "Forecast Board", "widgets": []},
        },
        {
            "id": "customer_segment",
            "name": "Customer Segment",
            "description": "RFM style segmentation",
            "queries": ["segment by Customer_ID", "show top 5 Customer by Sales"],
            "dashboard_template": {"name": "Customers", "widgets": []},
        },
        {
            "id": "ops_monitor",
            "name": "Ops Monitor",
            "description": "Schedule + threshold alerts",
            "queries": ["what if Sales dropped 10%"],
            "dashboard_template": {"name": "Ops", "widgets": []},
        },
        {
            "id": "finance_kpi",
            "name": "Finance KPI",
            "description": "P&L style KPIs",
            "queries": ["correlation heatmap", "describe Profit"],
            "dashboard_template": {"name": "Finance", "widgets": []},
        },
        {
            "id": "hr_analytics",
            "name": "HR Analytics",
            "description": "Attrition & headcount",
            "queries": ["segment by Department", "show outliers in Salary via zscore"],
            "dashboard_template": {"name": "HR", "widgets": []},
        },
        {
            "id": "supply_chain",
            "name": "Supply Chain",
            "description": "Lead time outliers",
            "queries": ["show outliers in Lead_Time via iqr"],
            "dashboard_template": {"name": "Supply", "widgets": []},
        },
        {
            "id": "marketing_mix",
            "name": "Marketing Mix",
            "description": "Channel mix & ROI",
            "queries": ["top 5 Channel by Spend", "forecast Spend for next 2 months"],
            "dashboard_template": {"name": "Marketing", "widgets": []},
        },
        {
            "id": "product_health",
            "name": "Product Health",
            "description": "Feature usage & churn",
            "queries": ["why did churn increase last month?", "segment by Product"],
            "dashboard_template": {"name": "Product", "widgets": []},
        },
    ]
    for t in templates:
        p = d / f"{t['id']}.json"
        if not p.exists():
            _atomic_write_json(p, t)
    return templates


@router.get("")
async def list_marketplace(kind: Optional[str] = None, user=Depends(get_current_user)):
    _ensure_marketplace_seed()
    d = _marketplace_dir()
    out = []
    for f in d.glob("*.json"):
        try:
            with open(f) as jf:
                data = json.load(jf)
            if kind and kind not in data.get("id", ""):
                continue
            out.append(
                {
                    "id": data["id"],
                    "name": data["name"],
                    "description": data.get("description", ""),
                    "queries": data.get("queries", []),
                }
            )
        except:
            continue
    return out


@router.get("/{mid}")
async def get_item(mid: str, user=Depends(get_current_user)):
    _ensure_marketplace_seed()
    p = _marketplace_dir() / f"{mid}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Marketplace item not found")
    with open(p) as f:
        return json.load(f)


@router.post("/{mid}/install")
async def install_item(mid: str, request: Request, user=Depends(get_current_user)):
    _ensure_marketplace_seed()
    p = _marketplace_dir() / f"{mid}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Marketplace item not found")
    with open(p) as f:
        tmpl = json.load(f)
    # Install into workspace: create dashboard with queries
    ws_id = user.get("workspace_id") or "default"
    # Need a dataset to attach? Use default dataset if provided in body, else first dataset
    body = {}
    try:
        body = await request.json()
    except:
        body = {}
    dataset_id = body.get("dataset_id")
    if not dataset_id:
        # try list first dataset
        from app.core.storage import list_datasets

        ds = list_datasets()
        if ds:
            dataset_id = ds[0]["id"]
        else:
            # create mock dataset not needed; just return template info
            return {
                "status": "installed",
                "workspace_id": ws_id,
                "template": tmpl,
                "note": "no dataset, dashboard not created",
            }
    # create dashboard
    try:
        from app.services.dashboard_service import create_dashboard

        dash = create_dashboard(
            dataset_id,
            tmpl.get("dashboard_template", {}).get("name", tmpl["name"]),
            tmpl.get("description", ""),
        )
        # add widgets for each query?
        from app.services.dashboard_service import add_widget

        for q in tmpl.get("queries", [])[:3]:
            try:
                add_widget(dash["id"], {"query": q, "title": q[:40]})
            except:
                pass
        # refresh dash
        from app.services.dashboard_service import get_dashboard

        full = get_dashboard(dash["id"])
        return {
            "status": "installed",
            "workspace_id": ws_id,
            "dashboard": full,
            "template": tmpl["id"],
        }
    except Exception as e:
        return {
            "status": "installed",
            "workspace_id": ws_id,
            "template": tmpl["id"],
            "dashboard_error": str(e)[:200],
        }
