"""Plugin API — BaseConnector + BaseAnalyzer, entry_points via importlib.metadata."""

import importlib.metadata
import pandas as pd
from typing import Dict, Any, List, Optional


class BaseConnector:
    """Implement for a new data source. Register via entry_points."""

    kind: str = "base"
    display_name: str = "Base"
    # params_schema describes frontend form fields: [{"name":"host","label":"Host","type":"text"}, ...]
    params_schema: List[Dict[str, Any]] = []

    def fetch(self, params: Dict[str, Any], limit: int = 1000) -> pd.DataFrame:
        """Return DataFrame from external source."""
        raise NotImplementedError

    def validate(self, params: Dict[str, Any]) -> Optional[str]:
        """Return error string if params invalid, else None."""
        return None


class BaseAnalyzer:
    """Implement for custom insight."""

    name: str = "base"

    def analyze(self, df: pd.DataFrame, query: str) -> Dict[str, Any]:
        raise NotImplementedError


_REGISTRY: Dict[str, BaseConnector] = {}


def register_connector(cls):
    """Decorator: @register_connector class MyConn(BaseConnector): kind='my'"""
    inst = cls()
    _REGISTRY[inst.kind] = inst
    return cls


def get_connector(kind: str) -> Optional[BaseConnector]:
    # Check manual registry first
    if kind in _REGISTRY:
        return _REGISTRY[kind]
    # Then entry_points
    try:
        eps = importlib.metadata.entry_points()
        # py3.10+ has group param
        try:
            for ep in eps.select(group="insightagent.connectors"):
                if ep.name == kind:
                    cls = ep.load()
                    return cls()
        except AttributeError:
            # old API
            for ep in eps.get("insightagent.connectors", []):
                if ep.name == kind:
                    cls = ep.load()
                    return cls()
    except Exception:
        pass
    return None


def list_connectors() -> List[Dict[str, Any]]:
    """List all connectors: manual + entry_points."""
    out = []
    seen = set()
    for kind, inst in _REGISTRY.items():
        out.append(
            {"kind": kind, "display_name": inst.display_name, "params_schema": inst.params_schema}
        )
        seen.add(kind)
    # entry_points
    try:
        eps = importlib.metadata.entry_points()
        try:
            eps_list = eps.select(group="insightagent.connectors")
        except AttributeError:
            eps_list = eps.get("insightagent.connectors", [])
        for ep in eps_list:
            if ep.name not in seen:
                try:
                    cls = ep.load()
                    inst = cls()
                    out.append(
                        {
                            "kind": ep.name,
                            "display_name": getattr(inst, "display_name", ep.name),
                            "params_schema": getattr(inst, "params_schema", []),
                        }
                    )
                    seen.add(ep.name)
                except Exception:
                    continue
    except Exception:
        pass
    return out


def get_analyzer(name: str) -> Optional[BaseAnalyzer]:
    try:
        eps = importlib.metadata.entry_points()
        try:
            for ep in eps.select(group="insightagent.analyzers"):
                if ep.name == name:
                    return ep.load()()
        except AttributeError:
            for ep in eps.get("insightagent.analyzers", []):
                if ep.name == name:
                    return ep.load()()
    except Exception:
        pass
    return None
