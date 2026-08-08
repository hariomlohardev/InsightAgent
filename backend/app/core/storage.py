import json
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd

from app.config import get_storage_path

def _datasets_dir() -> Path:
    d = get_storage_path() / "datasets"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _conversations_dir() -> Path:
    d = get_storage_path() / "conversations"
    d.mkdir(parents=True, exist_ok=True)
    return d

def save_dataset(file_path: Path, original_filename: str) -> str:
    """Copy file to storage and create meta. Returns dataset_id."""
    dataset_id = str(uuid.uuid4())[:8]
    dest_dir = _datasets_dir() / dataset_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "data.csv"
    # If excel, convert to csv? Keep original extension
    suffix = file_path.suffix.lower()
    if suffix in [".csv"]:
        shutil.copy(file_path, dest_file)
    elif suffix in [".xlsx", ".xls"]:
        # Convert to csv for uniform handling, keep original too
        shutil.copy(file_path, dest_dir / f"original{suffix}")
        df = pd.read_excel(file_path)
        df.to_csv(dest_file, index=False)
    elif suffix in [".json"]:
        shutil.copy(file_path, dest_dir / "original.json")
        df = pd.read_json(file_path)
        df.to_csv(dest_file, index=False)
    else:
        shutil.copy(file_path, dest_file)

    # Load to get shape
    try:
        df = pd.read_csv(dest_file, nrows=5)
        preview_cols = df.columns.tolist()
        # Full shape
        full_df = pd.read_csv(dest_file)
        rows = len(full_df)
        cols = len(full_df.columns)
    except Exception:
        rows, cols = 0, 0
        preview_cols = []

    meta = {
        "id": dataset_id,
        "original_filename": original_filename,
        "created_at": datetime.utcnow().isoformat(),
        "rows": rows,
        "columns": cols,
        "column_names": preview_cols,
        "file_path": str(dest_file),
    }
    with open(dest_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    return dataset_id

def list_datasets() -> List[Dict[str, Any]]:
    datasets = []
    for d in _datasets_dir().iterdir():
        if d.is_dir():
            meta_file = d / "meta.json"
            if meta_file.exists():
                with open(meta_file) as f:
                    datasets.append(json.load(f))
    # Sort by created_at desc
    datasets.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return datasets

def get_dataset_meta(dataset_id: str) -> Optional[Dict[str, Any]]:
    meta_file = _datasets_dir() / dataset_id / "meta.json"
    if not meta_file.exists():
        return None
    with open(meta_file) as f:
        return json.load(f)

def get_dataset_path(dataset_id: str) -> Optional[Path]:
    meta = get_dataset_meta(dataset_id)
    if not meta:
        return None
    p = Path(meta["file_path"])
    if p.exists():
        return p
    # Fallback
    alt = _datasets_dir() / dataset_id / "data.csv"
    if alt.exists():
        return alt
    return None

def load_dataset_df(dataset_id: str) -> pd.DataFrame:
    p = get_dataset_path(dataset_id)
    if not p or not p.exists():
        raise FileNotFoundError(f"Dataset {dataset_id} not found")
    # Try csv
    try:
        return pd.read_csv(p)
    except Exception:
        # Try excel original
        orig_xlsx = p.parent / "original.xlsx"
        orig_xls = p.parent / "original.xls"
        if orig_xlsx.exists():
            return pd.read_excel(orig_xlsx)
        if orig_xls.exists():
            return pd.read_excel(orig_xls)
        raise

def delete_dataset(dataset_id: str) -> bool:
    d = _datasets_dir() / dataset_id
    if d.exists():
        shutil.rmtree(d)
        return True
    return False

# Conversations

def save_conversation_message(dataset_id: str, conversation_id: str, role: str, content: Dict[str, Any]) -> str:
    """Append message to conversation file. Returns conversation_id."""
    if not conversation_id:
        conversation_id = str(uuid.uuid4())[:8]
    conv_file = _conversations_dir() / f"{conversation_id}.json"
    if conv_file.exists():
        with open(conv_file) as f:
            conv = json.load(f)
    else:
        conv = {
            "id": conversation_id,
            "dataset_id": dataset_id,
            "created_at": datetime.utcnow().isoformat(),
            "messages": []
        }
    msg = {
        "role": role,
        "timestamp": datetime.utcnow().isoformat(),
        **content
    }
    conv["messages"].append(msg)
    conv["updated_at"] = datetime.utcnow().isoformat()
    def _default(o):
        import numpy as np
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        return str(o)
    with open(conv_file, "w") as f:
        json.dump(conv, f, indent=2, default=_default)
    return conversation_id

def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    f = _conversations_dir() / f"{conversation_id}.json"
    if not f.exists():
        return None
    try:
        with open(f) as fv:
            return json.load(fv)
    except json.JSONDecodeError:
        # Corrupted file from earlier crash, remove or skip
        try:
            f.unlink()
        except:
            pass
        return None

def list_conversations(dataset_id: Optional[str] = None) -> List[Dict[str, Any]]:
    convs = []
    for f in _conversations_dir().glob("*.json"):
        try:
            with open(f) as fv:
                c = json.load(fv)
        except json.JSONDecodeError:
            # Skip corrupted files
            try:
                f.unlink()
            except:
                pass
            continue
        except Exception:
            continue
        if dataset_id is None or c.get("dataset_id") == dataset_id:
            convs.append(c)
    convs.sort(key=lambda x: x.get("updated_at", x.get("created_at", "")), reverse=True)
    return convs
