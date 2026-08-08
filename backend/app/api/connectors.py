from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.services import connector_service
from app.core.connectors import validate_sql
from app.core.security import SecurityError

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


class ConnectorCreate(BaseModel):
    kind: str  # postgres|mysql|sqlite|bigquery|sheets
    name: Optional[str] = None
    dsn: Optional[str] = None
    table: Optional[str] = None
    sheet_url: Optional[str] = None
    credentials_json: Optional[str] = None


class ConnectorResponse(BaseModel):
    id: str
    original_filename: str  # for DatasetResponse compat, we alias name
    name: Optional[str] = None
    kind: str
    rows: int
    columns: int
    column_names: List[str]
    created_at: str
    type: str = "connector"
    # extra
    sample_error: Optional[str] = None


class QueryRequest(BaseModel):
    sql: str
    limit: int = 500


@router.post("", status_code=201)
async def create_connector(body: ConnectorCreate):
    kind = (body.kind or "").lower().strip()
    if not kind:
        raise HTTPException(
            status_code=400, detail="kind required (postgres|mysql|sqlite|bigquery|sheets)"
        )
    # sheets can use dsn as sheet_url fallback
    sheet_url = body.sheet_url or (
        body.dsn if kind in ("sheets", "gsheets", "google_sheets") else None
    )
    dsn = body.dsn
    # For sheets, if user passed sheet_url in dsn, normalize
    if kind in ("sheets", "gsheets", "google_sheets") and not sheet_url:
        raise HTTPException(
            status_code=400, detail="sheets requires sheet_url (Google Sheets share link)"
        )
    try:
        meta = connector_service.create_connector(
            kind=kind,
            name=body.name,
            dsn=dsn,
            table=body.table,
            sheet_url=sheet_url,
            credentials_json=body.credentials_json,
        )
        # Return dataset-like response but also connector detail
        # Map to ConnectorResponse-ish
        return meta
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_connectors():
    try:
        # Return connectors as dataset-style metas (from connectors dir)
        # But also ensure list from connectors service
        conns = connector_service.list_connectors()
        # Also ensure dataset-style for frontend dataset list: frontend will use /api/datasets to show all
        # This endpoint returns raw connectors
        return conns
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{cid}")
async def get_connector(cid: str):
    c = connector_service.get_connector(cid)
    if not c:
        # Try dataset meta
        from app.core import storage

        meta = storage.get_dataset_meta(cid)
        if meta and meta.get("type") == "connector":
            return meta.get("connector") or meta
        raise HTTPException(status_code=404, detail="Connector not found")
    return c


@router.delete("/{cid}")
async def delete_connector(cid: str):
    # Try both
    ok = connector_service.delete_connector(cid)
    if not ok:
        from app.core import storage

        # Try dataset delete
        if storage.delete_dataset(cid):
            ok = True
    if not ok:
        raise HTTPException(status_code=404, detail="Connector not found")
    return {"status": "deleted", "id": cid}


@router.post("/{cid}/query")
async def query_connector(cid: str, body: QueryRequest):
    if not body.sql.strip():
        raise HTTPException(status_code=400, detail="sql cannot be empty")
    try:
        validate_sql(body.sql)
    except SecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        res = connector_service.query_connector(cid, body.sql, limit=body.limit)
        return res
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        # Could be driver missing or Sheets private
        # For bigquery not configured, return 501
        msg = str(e)
        if "not installed" in msg.lower() or "not configured" in msg.lower():
            raise HTTPException(status_code=501, detail=msg)
        raise HTTPException(status_code=500, detail=msg)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# Also expose a test endpoint for connection health
@router.post("/{cid}/test")
async def test_connector(cid: str):
    try:
        res = connector_service.query_connector(cid, "SELECT 1 as _test_col", limit=1)
        return {"status": "ok", "rows": res.get("rows"), "preview": res.get("preview")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")
