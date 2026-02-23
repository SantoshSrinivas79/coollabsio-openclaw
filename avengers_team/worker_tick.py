from __future__ import annotations

import argparse
import os
from datetime import timedelta
from pathlib import Path

from avengers_team.executor import run_executor
from avengers_team.lib_queue import (
    append_jsonl,
    atomic_lock_create,
    current_tasks_root,
    lock_remove,
    now_iso_local,
    parse_iso,
    read_json,
    task_paths,
    write_json,
    write_text,
)
from avengers_team.packager import build_exec_packet
from avengers_team.templates import review_instructions_md
from avengers_team.validate import validate_result


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def read_meta(path: Path) -> dict:
    value = read_json(path, {})
    return value if isinstance(value, dict) else {}


def list_tasks(tasks_root: Path) -> list[Path]:
    if not tasks_root.exists():
        return []
    return [d for d in sorted(tasks_root.iterdir()) if d.is_dir()]


def deps_done(tasks_root: Path, depends_on: list[str]) -> bool:
    for dep_id in depends_on:
        dep_dir = next(tasks_root.glob(f"{dep_id}_*/"), None)
        if not dep_dir:
            return False
        meta = read_meta(dep_dir / "meta.json")
        if meta.get("state") != "done":
            return False
    return True


def find_tasks_by_state(tasks_root: Path, role: str, states: tuple[str, ...]) -> list[Path]:
    out = []
    for d in list_tasks(tasks_root):
        meta = read_meta(d / "meta.json")
        if meta.get("role") == role and meta.get("state") in states:
            out.append(d)
    return out


def find_claimable(tasks_root: Path, role: str) -> list[Path]:
    candidates: list[tuple[int, Path]] = []
    for d in list_tasks(tasks_root):
        meta = read_meta(d / "meta.json")
        if meta.get("state") != "queued":
            continue
        if meta.get("role") != role:
            continue
        if not deps_done(tasks_root, meta.get("depends_on", [])):
            continue
        candidates.append((int(meta.get("priority", 0)), d))
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in candidates]


def claim_task(task_dir: Path, role: str, worker_id: str, lease_seconds: int) -> bool:
    tp = task_paths(task_dir)
    if not atomic_lock_create(tp.lock):
        return False

    meta = read_meta(tp.meta_json)
    if meta.get("state") != "queued" or meta.get("role") != role:
        lock_remove(tp.lock)
        return False

    meta["state"] = "in_progress"
    meta["started_at"] = now_iso_local()
    meta["worker_id"] = worker_id
    write_json(tp.meta_json, meta)

    write_json(
        tp.claim_json,
        {
            "claimed_by": worker_id,
            "claimed_at": now_iso_local(),
            "lease_seconds": lease_seconds,
        },
    )
    write_json(tp.heartbeat_json, {"last_heartbeat_at": now_iso_local()})
    return True


def move_to_awaiting_review(task_dir: Path, review_window_seconds: int) -> None:
    tp = task_paths(task_dir)
    meta = read_meta(tp.meta_json)
    deadline = (parse_iso(now_iso_local()) + timedelta(seconds=review_window_seconds)).isoformat()

    meta["state"] = "awaiting_review"
    meta["review_deadline_at"] = deadline
    meta["awaiting_review_at"] = now_iso_local()
    write_json(tp.meta_json, meta)

    write_text(task_dir / "REVIEW.md", review_instructions_md(meta.get("id", task_dir.name), deadline))


def mark_failed(workspace: Path, task_dir: Path, reason: str) -> None:
    tp = task_paths(task_dir)
    meta = read_meta(tp.meta_json)
    meta["state"] = "failed"
    meta["failed_at"] = now_iso_local()
    meta["fail_reason"] = reason
    write_json(tp.meta_json, meta)
    append_jsonl(
        workspace / "logs" / "executor_failures.jsonl",
        {
            "ts": now_iso_local(),
            "task_id": meta.get("id", task_dir.name.split("_")[0]),
            "role": meta.get("role", ""),
            "reason": reason[:2000],
        },
    )
    lock_remove(tp.lock)


def heartbeat(task_dir: Path) -> None:
    tp = task_paths(task_dir)
    write_json(tp.heartbeat_json, {"last_heartbeat_at": now_iso_local()})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--role",
        required=True,
        choices=[
            "captain-america",
            "alex-hormozi",
            "brian-tracy",
            "april-dunford",
            "russell-brunson",
            "steve-blank",
        ],
    )
    args = ap.parse_args()

    workspace = Path(os.environ.get("WORKSPACE_ROOT", "/workspace"))
    tasks_root = current_tasks_root(workspace)

    review_window_seconds = env_int("REVIEW_WINDOW_SECONDS", 300)
    lease_seconds = env_int("TASK_TIMEOUT_SECONDS", 600)
    worker_id = f"tick-{args.role}-1"

    # Keep heartbeat alive for awaiting-review tasks only.
    awaiting = find_tasks_by_state(tasks_root, args.role, ("awaiting_review",))
    for d in awaiting:
        heartbeat(d)
    if awaiting:
        return

    # Do not refresh heartbeat for in-progress tasks from a separate tick.
    # If execution crashed, orchestrator timeout logic should reclaim/requeue.
    in_progress = find_tasks_by_state(tasks_root, args.role, ("in_progress",))
    if in_progress:
        return

    claimables = find_claimable(tasks_root, args.role)
    if not claimables:
        return

    task_dir = claimables[0]
    if not claim_task(task_dir, args.role, worker_id, lease_seconds):
        return

    tp = task_paths(task_dir)

    try:
        exec_md = build_exec_packet(workspace, task_dir)
        run_executor(args.role, exec_md, tp.result_md)
        validate_result(tp.result_md)
        move_to_awaiting_review(task_dir, review_window_seconds)
    except Exception as e:
        mark_failed(workspace, task_dir, str(e))


if __name__ == "__main__":
    main()
