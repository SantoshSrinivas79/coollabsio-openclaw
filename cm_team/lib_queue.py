from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso_local() -> str:
    return datetime.now().astimezone().isoformat()


def parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding="utf-8") as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = tmp.name
    os.replace(tmp_path, path)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_text(path: Path, content: str) -> None:
    atomic_write_text(path, content)


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    atomic_write_json(path, data)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return default if value is None else value
    except Exception:
        return default


def append_jsonl(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(data, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def atomic_lock_create(lock_path: Path) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(lock_path), flags)
    except FileExistsError:
        return False
    os.close(fd)
    return True


def lock_remove(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return


@dataclass(frozen=True)
class TaskPaths:
    task_dir: Path
    lock: Path
    claim_json: Path
    heartbeat_json: Path
    meta_json: Path
    task_md: Path
    result_md: Path
    feedback_md: Path


def task_paths(task_dir: Path) -> TaskPaths:
    return TaskPaths(
        task_dir=task_dir,
        lock=task_dir / "LOCK",
        claim_json=task_dir / "claim.json",
        heartbeat_json=task_dir / "heartbeat.json",
        meta_json=task_dir / "meta.json",
        task_md=task_dir / "task.md",
        result_md=task_dir / "result.md",
        feedback_md=task_dir / "user_feedback.md",
    )


def current_run_pointer(runs_root: Path) -> Path:
    return runs_root / "CURRENT_RUN.txt"


def get_current_run_name(runs_root: Path) -> str:
    ptr = current_run_pointer(runs_root)
    if ptr.exists():
        name = ptr.read_text(encoding="utf-8").strip()
        if name:
            return name
    return "current"


def get_current_run_dir(runs_root: Path) -> Path:
    run_name = get_current_run_name(runs_root)
    run_dir = runs_root / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def set_current_run_dir(runs_root: Path, name: str) -> Path:
    ptr = current_run_pointer(runs_root)
    ptr.write_text(name, encoding="utf-8")
    run_dir = runs_root / name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def tasks_root_for_run(run_dir: Path) -> Path:
    tasks_root = run_dir / "tasks"
    tasks_root.mkdir(parents=True, exist_ok=True)
    return tasks_root


def current_tasks_root(workspace: Path) -> Path:
    runs_root = workspace / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    run_dir = get_current_run_dir(runs_root)
    return tasks_root_for_run(run_dir)
