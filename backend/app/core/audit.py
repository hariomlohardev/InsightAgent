import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from app.config import get_storage_path

def _audit_dir() -> Path:
    d = get_storage_path() / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d

def log(action: str, user: Optional[Dict[str, Any]], dataset_id: Optional[str] = None, dashboard_id: Optional[str] = None, ip: str = "", extra: str = ""):
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = _audit_dir() / f"{today}.jsonl"
        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "user": (user.get("email") if user else "anon") if isinstance(user, dict) else str(user or "anon"),
            "user_id": user.get("id") if isinstance(user, dict) else None,
            "role": user.get("role") if isinstance(user, dict) else None,
            "action": action,
            "dataset_id": dataset_id,
            "dashboard_id": dashboard_id,
            "ip": ip,
            "extra": extra[:300] if extra else "",
        }
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        # Rotate: keep 30 days max
        try:
            import time
            now = time.time()
            for p in _audit_dir().glob("*.jsonl"):
                if now - p.stat().st_mtime > 30 * 86400:
                    try:
                        p.unlink()
                    except:
                        pass
        except:
            pass
        return entry
    except:
        return None

def list_audit(dataset_id: Optional[str] = None, limit: int = 100, user_email: Optional[str] = None) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    # Read all jsonl sorted by date desc, but we scan last few files
    files = sorted(_audit_dir().glob("*.jsonl"), reverse=True)
    # If many files, limit to 5 most recent (covers ~5 days * up to many entries enough for 100)
    for f in files[:10]:
        try:
            with open(f) as jf:
                for line in jf:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                        if dataset_id and e.get("dataset_id") != dataset_id:
                            continue
                        if user_email and e.get("user") != user_email:
                            continue
                        entries.append(e)
                    except:
                        continue
        except:
            continue
        if len(entries) >= limit:
            break
    # Sort by at desc (file already but cross files)
    entries.sort(key=lambda x: x.get("at",""), reverse=True)
    return entries[:limit]
