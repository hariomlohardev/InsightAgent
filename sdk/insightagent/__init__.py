"""InsightAgent SDK — httpx client for local or cloud backend."""
import os
import io
from typing import Optional
import httpx
import pandas as pd

class InsightAgent:
    """Thin wrapper around Backend REST. Works with CLOUD=false (local) and cloud via INSIGHTAGENT_URL."""
    def __init__(self, url: str = None, api_key: str = None, timeout: int = 30):
        self.url = (url or os.getenv("INSIGHTAGENT_URL") or os.getenv("BACKEND_URL") or "http://localhost:8000").rstrip("/")
        self.api_key = api_key or os.getenv("INSIGHTAGENT_API_KEY")
        self.timeout = timeout
        self._dataset_id: Optional[str] = None

    def _headers(self):
        h = {}
        if self.api_key:
            # Support both Bearer and X-API-Key
            if self.api_key.startswith("sk-") or "." in self.api_key:
                h["Authorization"] = f"Bearer {self.api_key}"
            else:
                h["X-API-Key"] = self.api_key
        return h

    def health(self) -> dict:
        r = httpx.get(f"{self.url}/health", timeout=5)
        r.raise_for_status()
        return r.json()

    def upload(self, df: pd.DataFrame = None, path: str = None, name: str = "upload.csv") -> str:
        """Upload df or file path, returns dataset_id. Also sets as current."""
        if df is not None:
            buf = io.BytesIO()
            df.to_csv(buf, index=False)
            buf.seek(0)
            files = {"file": (name, buf, "text/csv")}
        elif path:
            p = path
            with open(p, "rb") as f:
                files = {"file": (name, f.read(), "text/csv")}
        else:
            raise ValueError("Provide df or path")
        r = httpx.post(f"{self.url}/api/datasets/upload", files=files, headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        self._dataset_id = r.json()["id"]
        return self._dataset_id

    def chat(self, query: str, dataset_id: str = None, timeout: int = None) -> dict:
        did = dataset_id or self._dataset_id
        if not did:
            raise ValueError("No dataset_id — upload first or pass dataset_id")
        payload = {"dataset_id": did, "query": query}
        r = httpx.post(f"{self.url}/api/chat", json=payload, headers=self._headers(), timeout=timeout or self.timeout)
        r.raise_for_status()
        return r.json()

    def profile(self, dataset_id: str = None) -> dict:
        did = dataset_id or self._dataset_id
        r = httpx.get(f"{self.url}/api/datasets/{did}", headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def list_datasets(self, q: str = None) -> list:
        url = f"{self.url}/api/datasets"
        if q:
            url += f"?q={q}"
        r = httpx.get(url, headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def dashboard(self, dataset_id: str = None) -> list:
        did = dataset_id or self._dataset_id
        r = httpx.get(f"{self.url}/api/dashboards?dataset_id={did}", headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

__all__ = ["InsightAgent"]
