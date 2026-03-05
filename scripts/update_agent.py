import argparse
from typing import Any, Dict, List, Tuple

from utils import read_json, write_json, now_iso


def _json_pointer_escape(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def _set_path(obj: Dict, path: List[str], value: Any) -> None:
    cur = obj
    for p in path[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[path[-1]] = value


def _get_path(obj: Dict, path: List[str]) -> Any:
    cur = obj
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def build_patch_and_changelog(v1: Dict, updates: Dict) -> Tuple[List[Dict], List[Dict]]:
    """
    updates: partial dict containing only onboarding-confirmed fields.
    Returns (json_patch_ops, changelog_entries)
    """
    patch: List[Dict] = []
    changes: List[Dict] = []

    # ignore private meta
    updates = {k: v for k, v in updates.items() if k != "_meta"}

    def add_replace(path: List[str], new_val: Any):
        old_val = _get_path(v1, path)
        op = "replace" if old_val is not None else "add"
        patch.append({
            "op": op,
            "path": "/" + "/".join(_json_pointer_escape(p) for p in path),
            "value": new_val
        })
        changes.append({
            "field": ".".join(path),
            "old": old_val,
            "new": new_val,
            "reason": "Confirmed on onboarding input."
        })

    # business_hours object replace (only if provided)
    if "business_hours" in updates:
        add_replace(["business_hours"], updates["business_hours"])

    if "emergency_definition" in updates:
        add_replace(["emergency_definition"], updates["emergency_definition"])

    if "integration_constraints" in updates:
        # merge append without dropping previous (but de-dup)
        prev = v1.get("integration_constraints", []) or []
        merged = prev[:]
        for x in updates["integration_constraints"]:
            if x.lower().strip() not in {p.lower().strip() for p in merged}:
                merged.append(x)
        add_replace(["integration_constraints"], merged)

    if "call_transfer_rules" in updates:
        for k, v in updates["call_transfer_rules"].items():
            add_replace(["call_transfer_rules", k], v)

    if "emergency_routing_rules" in updates:
        for k, v in updates["emergency_routing_rules"].items():
            add_replace(["emergency_routing_rules", k], v)

    return patch, changes


def apply_patch(v1: Dict, patch_ops: List[Dict]) -> Dict:
    v2 = read_json_from_obj(v1)
    for op in patch_ops:
        path = op["path"].lstrip("/").split("/") if op.get("path") else []
        path = [p.replace("~1", "/").replace("~0", "~") for p in path]
        if op["op"] in ("add", "replace"):
            _set_path(v2, path, op["value"])
        else:
            raise ValueError(f"Unsupported op: {op['op']}")
    return v2


def read_json_from_obj(obj: Any) -> Any:
    # cheap deep-copy without extra deps
    import json
    return json.loads(json.dumps(obj))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v1_memo", required=True)
    ap.add_argument("--updates_json", required=True, help="Onboarding updates JSON file")
    ap.add_argument("--out_v2_memo", required=True)
    ap.add_argument("--out_patch", required=True)
    ap.add_argument("--out_changelog", required=True)
    args = ap.parse_args()

    v1 = read_json(args.v1_memo)
    updates = read_json(args.updates_json)

    patch_ops, change_entries = build_patch_and_changelog(v1, updates)
    v2 = apply_patch(v1, patch_ops)

    # Version + sources update
    v2["version"] = "v2"
    v2.setdefault("sources", {})
    meta = updates.get("_meta", {})
    if meta:
        v2["sources"]["onboarding_source_file"] = meta.get("source_file", "")
        v2["sources"]["onboarding_input_hash"] = meta.get("input_hash", "")
    v2.setdefault("meta", {})
    v2["meta"]["updated_at"] = now_iso()

    changelog = {
        "account_id": v1.get("account_id"),
        "from_version": "v1",
        "to_version": "v2",
        "changes": change_entries,
        "conflicts_resolved": [],
        "timestamp": now_iso()
    }

    write_json(args.out_patch, patch_ops)
    write_json(args.out_changelog, changelog)
    write_json(args.out_v2_memo, v2)


if __name__ == "__main__":
    main()