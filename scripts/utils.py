import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional


ACCT_RE = re.compile(r"(acct_\d+)", re.IGNORECASE)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def ensure_dir(path: str) -> None:
    directory = path if os.path.splitext(path)[1] == "" else os.path.dirname(path)
    if directory:  # prevents "" case
        os.makedirs(directory, exist_ok=True)

def write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_account_id(filename: str) -> str:
    m = ACCT_RE.search(filename)
    if not m:
        raise ValueError(f"Could not infer account_id from filename: {filename}. "
                         f"Expected pattern like acct_001_demo.txt")
    return m.group(1).lower()


def append_jsonl(path: str, record: Dict[str, Any]) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def already_processed(run_log_path: str, key: Dict[str, str]) -> bool:
    """
    Idempotency check: if exact (account_id, stage, input_hash) exists in run_log.jsonl, skip.
    """
    if not os.path.exists(run_log_path):
        return False
    target = (key["account_id"], key["stage"], key["input_hash"])
    with open(run_log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if (obj.get("account_id"), obj.get("stage"), obj.get("input_hash")) == target:
                return True
    return False