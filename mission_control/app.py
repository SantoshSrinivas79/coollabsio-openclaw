from __future__ import annotations

import json
import os
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def safe_read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return default


def safe_read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return value if value is not None else default


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def normalized_status(state: str) -> str:
    known = {
        "queued",
        "in_progress",
        "awaiting_review",
        "done",
        "failed",
        "blocked",
        "stale",
    }
    return state if state in known else "other"


def extract_objective(task_md: str, fallback: str) -> str:
    if not task_md.strip():
        return fallback

    lines = [line.rstrip() for line in task_md.splitlines()]
    for idx, line in enumerate(lines):
        if line.strip().lower() in {"## objective", "# objective", "objective:"}:
            for candidate in lines[idx + 1 :]:
                val = candidate.strip(" -\t")
                if val and not val.startswith("#"):
                    return val

    for line in lines:
        val = line.strip()
        if val and not val.startswith("#"):
            return val

    return fallback


def default_data_root() -> Path:
    configured = os.environ.get("MISSION_CONTROL_DATA_ROOT", "").strip()
    if configured:
        return Path(configured)
    container_path = Path("/data")
    if container_path.exists():
        return container_path
    return Path.cwd() / "data"


class MissionControlStore:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root

    def discover_instances(self) -> list[dict[str, str]]:
        instances: list[dict[str, str]] = []
        if not self.data_root.exists():
            return instances

        for child in sorted(self.data_root.iterdir()):
            if not child.is_dir():
                continue
            runs_dir = child / "runs"
            if not runs_dir.is_dir():
                continue
            instances.append(
                {
                    "id": child.name,
                    "label": child.name.replace("_", " ").title(),
                    "path": str(child),
                }
            )
        return instances

    def list_runs(self, instance_id: str) -> list[dict[str, Any]]:
        workspace = self.data_root / instance_id
        runs_root = workspace / "runs"
        if not runs_root.is_dir():
            return []

        current_run_name = safe_read_text(runs_root / "CURRENT_RUN.txt", "").strip()
        out: list[dict[str, Any]] = []

        for entry in runs_root.iterdir():
            if not entry.is_dir():
                continue
            task_count = len(self._collect_task_refs(entry))
            out.append(
                {
                    "name": entry.name,
                    "is_current": entry.name == current_run_name,
                    "task_count": task_count,
                    "mtime": entry.stat().st_mtime,
                }
            )

        out.sort(key=lambda item: (not item["is_current"], -item["mtime"], item["name"]))
        return out

    def resolve_run_dir(self, instance_id: str, run_name: str | None) -> tuple[Path | None, str | None]:
        workspace = self.data_root / instance_id
        runs_root = workspace / "runs"
        if not runs_root.is_dir():
            return None, None

        requested = (run_name or "current").strip()
        if requested == "current":
            current_name = safe_read_text(runs_root / "CURRENT_RUN.txt", "").strip() or "current"
            run_dir = runs_root / current_name
            if run_dir.is_dir():
                return run_dir, current_name

        explicit = runs_root / requested
        if explicit.is_dir():
            return explicit, requested

        runs = self.list_runs(instance_id)
        if not runs:
            return None, None

        fallback = runs[0]["name"]
        fallback_dir = runs_root / fallback
        if fallback_dir.is_dir():
            return fallback_dir, fallback
        return None, None

    def _collect_task_refs(self, run_dir: Path) -> list[tuple[str, Path]]:
        refs: list[tuple[str, Path]] = []

        tasks_root = run_dir / "tasks"
        if tasks_root.is_dir():
            for task_dir in sorted([d for d in tasks_root.iterdir() if d.is_dir()]):
                refs.append((f"tasks/{task_dir.name}", task_dir))

        replaced_root = run_dir / "_replaced_tasks"
        if replaced_root.is_dir():
            for batch_dir in sorted([d for d in replaced_root.iterdir() if d.is_dir()], reverse=True):
                for task_dir in sorted([d for d in batch_dir.iterdir() if d.is_dir()]):
                    refs.append((f"_replaced_tasks/{batch_dir.name}/{task_dir.name}", task_dir))

        return refs

    def _build_task_card(self, task_ref: str, task_dir: Path) -> dict[str, Any]:
        meta = safe_read_json(task_dir / "meta.json", {})
        if not isinstance(meta, dict):
            meta = {}

        task_id = str(meta.get("id") or task_dir.name.split("_")[0])
        role = str(meta.get("role") or "unassigned")
        state = normalized_status(str(meta.get("state") or "queued"))
        priority = int(meta.get("priority") or 0)
        worker_id = str(meta.get("worker_id") or "")

        started_at = str(meta.get("started_at") or "")
        ended_at = ""
        for key in (
            "approved_at",
            "auto_approved_at",
            "failed_at",
            "blocked_at",
            "stale_at",
            "done_at",
        ):
            value = str(meta.get(key) or "")
            if value:
                ended_at = value
                break

        task_md = safe_read_text(task_dir / "task.md", "")
        result_md = safe_read_text(task_dir / "result.md", "")

        objective = extract_objective(task_md, str(meta.get("slug") or task_id))

        return {
            "id": task_id,
            "name": task_dir.name,
            "task_ref": task_ref,
            "objective": objective,
            "state": state,
            "agent": role,
            "worker_id": worker_id,
            "priority": priority,
            "depends_on": meta.get("depends_on", []),
            "created_at": str(meta.get("created_at") or ""),
            "started_at": started_at,
            "ended_at": ended_at,
            "task_excerpt": task_md[:1600],
            "result_excerpt": result_md[:2400],
        }

    def task_detail(self, instance_id: str, run_name: str | None, task_name: str) -> dict[str, Any] | None:
        run_dir, actual_run_name = self.resolve_run_dir(instance_id, run_name)
        if run_dir is None or actual_run_name is None:
            return None

        tasks_root = run_dir / "tasks"

        if not task_name:
            return None

        task_name = task_name.strip()
        task_dir: Path | None = None
        task_ref = task_name

        if "/" in task_name:
            rel = Path(task_name)
            if rel.is_absolute() or ".." in rel.parts:
                return None
            candidate = run_dir / rel
            if candidate.is_dir():
                task_dir = candidate
            else:
                return None
        else:
            direct = tasks_root / task_name
            if direct.is_dir():
                task_dir = direct
                task_ref = f"tasks/{task_name}"
            else:
                matches = [item for item in self._collect_task_refs(run_dir) if item[1].name == task_name or item[1].name.startswith(f"{task_name}_")]
                if matches:
                    task_ref, task_dir = matches[0]

        if task_dir is None:
            return None

        base = self._build_task_card(task_ref, task_dir)
        base["task_markdown"] = safe_read_text(task_dir / "task.md", "")
        base["result_markdown"] = safe_read_text(task_dir / "result.md", "")
        base["review_markdown"] = safe_read_text(task_dir / "REVIEW.md", "")
        base["meta"] = safe_read_json(task_dir / "meta.json", {})
        base["instance"] = instance_id
        base["run"] = actual_run_name
        return base

    def run_snapshot(self, instance_id: str, run_name: str | None) -> dict[str, Any]:
        run_dir, actual_run_name = self.resolve_run_dir(instance_id, run_name)
        if run_dir is None or actual_run_name is None:
            return {
                "instance": instance_id,
                "run": None,
                "generated_at": now_iso(),
                "columns": {key: [] for key in ["queued", "in_progress", "awaiting_review", "done", "failed", "blocked", "stale", "other"]},
                "stats": {},
                "run_context": {"request": "", "status": "", "final": ""},
                "run_sequence": [],
            }

        columns: dict[str, list[dict[str, Any]]] = {
            "queued": [],
            "in_progress": [],
            "awaiting_review": [],
            "done": [],
            "failed": [],
            "blocked": [],
            "stale": [],
            "other": [],
        }
        run_sequence: list[dict[str, Any]] = []

        for task_ref, task_dir in self._collect_task_refs(run_dir):
            card = self._build_task_card(task_ref, task_dir)
            columns[card["state"]].append(card)
            run_sequence.append(
                {
                    "id": card["id"],
                    "name": card["name"],
                    "objective": card["objective"],
                    "state": card["state"],
                    "agent": card["agent"],
                    "priority": card["priority"],
                    "task_ref": card["task_ref"],
                    "created_at": card["created_at"],
                    "started_at": card["started_at"],
                    "ended_at": card["ended_at"],
                }
            )

        for key, values in columns.items():
            if key == "queued":
                values.sort(key=lambda t: (-int(t.get("priority") or 0), t.get("created_at") or ""))
            elif key in {"in_progress", "awaiting_review"}:
                values.sort(key=lambda t: (t.get("started_at") or "", t.get("id") or ""), reverse=True)
            else:
                values.sort(key=lambda t: (t.get("ended_at") or t.get("created_at") or "", t.get("id") or ""), reverse=True)

        stats = {key: len(values) for key, values in columns.items()}
        stats["total"] = sum(stats.values())
        run_sequence.sort(
            key=lambda t: (
                parse_iso(str(t.get("started_at") or "")) or parse_iso(str(t.get("created_at") or "")) or datetime.min,
                str(t.get("id") or ""),
            )
        )

        return {
            "instance": instance_id,
            "run": actual_run_name,
            "generated_at": now_iso(),
            "columns": columns,
            "stats": stats,
            "run_sequence": run_sequence,
            "run_context": {
                "request": safe_read_text(run_dir / "run_request.md", ""),
                "status": safe_read_text(run_dir / "status.md", ""),
                "final": safe_read_text(run_dir / "final.md", ""),
            },
        }


class RequestHandler(BaseHTTPRequestHandler):
    store = MissionControlStore(default_data_root())

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        return

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _html(self, html: str) -> None:
        raw = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_head_only(self, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/healthz", "/api/instances", "/api/kanban", "/api/task"}:
            content_type = "text/html; charset=utf-8" if parsed.path == "/" else "application/json; charset=utf-8"
            self._send_head_only(content_type)
            return
        self._send_head_only("application/json; charset=utf-8", HTTPStatus.NOT_FOUND)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/healthz":
            self._json({"ok": True, "ts": now_iso()})
            return

        if parsed.path == "/api/instances":
            instances = self.store.discover_instances()
            for instance in instances:
                instance["runs"] = self.store.list_runs(instance["id"])
            self._json({"instances": instances, "generated_at": now_iso()})
            return

        if parsed.path == "/api/kanban":
            instance = (qs.get("instance") or [""])[0].strip()
            run = (qs.get("run") or ["current"])[0].strip() or "current"
            if not instance:
                self._json({"error": "Missing required query parameter: instance"}, HTTPStatus.BAD_REQUEST)
                return
            self._json(self.store.run_snapshot(instance, run))
            return

        if parsed.path == "/api/task":
            instance = (qs.get("instance") or [""])[0].strip()
            run = (qs.get("run") or ["current"])[0].strip() or "current"
            task = (qs.get("task") or [""])[0].strip()
            if not instance or not task:
                self._json({"error": "Missing required query parameters: instance, task"}, HTTPStatus.BAD_REQUEST)
                return
            detail = self.store.task_detail(instance, run, task)
            if detail is None:
                self._json({"error": "Task not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(detail)
            return

        if parsed.path == "/":
            self._html(INDEX_HTML)
            return

        self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)


INDEX_HTML = (Path(__file__).with_name("index.html")).read_text(encoding="utf-8")


def main() -> None:
    host = os.environ.get("MISSION_CONTROL_HOST", "0.0.0.0")
    port = env_int("MISSION_CONTROL_PORT", 8099)
    server = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"Mission Control listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
