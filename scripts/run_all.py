import argparse
import glob
import os
import json
import subprocess
from typing import List

from utils import (
    ensure_dir,
    extract_account_id,
    file_hash,
    write_json,
    append_jsonl,
    already_processed,
    now_iso,
    read_json,
)

def _py(cmd: List[str]) -> str:
    # run python module/script and capture stdout
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDERR:\n{p.stderr}")
    return p.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo_dir", required=True)
    ap.add_argument("--onboarding_dir", required=True)
    ap.add_argument("--outputs_dir", required=True)
    args = ap.parse_args()

    outputs_dir = args.outputs_dir
    run_log = os.path.join(outputs_dir, "run_log.jsonl")
    ensure_dir(outputs_dir)

    # ----------------------------
    # Pipeline A: demo -> v1
    # ----------------------------
    demo_files = sorted(glob.glob(os.path.join(args.demo_dir, "*.txt")))
    for fpath in demo_files:
        account_id = extract_account_id(os.path.basename(fpath))
        h = file_hash(fpath)
        key = {"account_id": account_id, "stage": "demo", "input_hash": h}
        if already_processed(run_log, key):
            continue

        acct_root = os.path.join(outputs_dir, "accounts", account_id)
        v1_dir = os.path.join(acct_root, "v1")
        ensure_dir(v1_dir)

        # Extract v1 memo (demo)
        memo_stdout = _py(["python", "scripts/extract_memo.py", "--input", fpath, "--stage", "demo"])
        memo = eval(memo_stdout) if memo_stdout.startswith("{") else json.loads(memo_stdout)  # safe enough for our prints
        v1_memo_path = os.path.join(v1_dir, "memo.json")
        write_json(v1_memo_path, memo)

        # Agent spec v1
        v1_agent_path = os.path.join(v1_dir, "agent_spec.json")
        _py(["python", "scripts/generate_agent_spec.py", "--memo_path", v1_memo_path, "--out_path", v1_agent_path, "--version", "v1"])

        # Source metadata
        source = {"stage": "demo", "file": fpath, "input_hash": h, "generated_at": now_iso()}
        write_json(os.path.join(v1_dir, "source.json"), source)

        append_jsonl(run_log, {**key, "status": "ok", "ts": now_iso()})

    # ----------------------------
    # Pipeline B: onboarding -> v2
    # ----------------------------
    onboarding_files = sorted(glob.glob(os.path.join(args.onboarding_dir, "*.txt")))
    for fpath in onboarding_files:
        account_id = extract_account_id(os.path.basename(fpath))
        h = file_hash(fpath)
        key = {"account_id": account_id, "stage": "onboarding", "input_hash": h}
        if already_processed(run_log, key):
            continue

        acct_root = os.path.join(outputs_dir, "accounts", account_id)
        v1_memo_path = os.path.join(acct_root, "v1", "memo.json")
        if not os.path.exists(v1_memo_path):
            append_jsonl(run_log, {**key, "status": "error", "error": "Missing v1 memo for account", "ts": now_iso()})
            continue

        v2_dir = os.path.join(acct_root, "v2")
        ensure_dir(v2_dir)

        # Extract onboarding updates (partial dict)
        updates_stdout = _py(["python", "scripts/extract_memo.py", "--input", fpath, "--stage", "onboarding"])
        updates = eval(updates_stdout) if updates_stdout.startswith("{") else json.loads(updates_stdout)

        updates_path = os.path.join(acct_root, "onboarding_updates.json")
        write_json(updates_path, updates)

        # Build v2 via patch + changelog
        patch_path = os.path.join(acct_root, "patch.json")
        changelog_path = os.path.join(acct_root, "changelog.json")
        v2_memo_path = os.path.join(v2_dir, "memo.json")

        _py([
            "python", "scripts/update_agent.py",
            "--v1_memo", v1_memo_path,
            "--updates_json", updates_path,
            "--out_v2_memo", v2_memo_path,
            "--out_patch", patch_path,
            "--out_changelog", changelog_path
        ])

        # Agent spec v2
        v2_agent_path = os.path.join(v2_dir, "agent_spec.json")
        _py(["python", "scripts/generate_agent_spec.py", "--memo_path", v2_memo_path, "--out_path", v2_agent_path, "--version", "v2"])

        # Source metadata
        source = {"stage": "onboarding", "file": fpath, "input_hash": h, "generated_at": now_iso()}
        write_json(os.path.join(v2_dir, "source.json"), source)

        append_jsonl(run_log, {**key, "status": "ok", "ts": now_iso()})

    print("Done. Outputs written to:", outputs_dir)


if __name__ == "__main__":
    main()