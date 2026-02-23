from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timedelta

import requests

from cm_team.lib_queue import (
    current_tasks_root,
    get_current_run_name as get_current_run_name_from_root,
    parse_iso,
    read_json,
    read_text,
    write_json,
    write_text,
)


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


WORKSPACE = Path(env_str("WORKSPACE_ROOT", "/workspace"))
BOT_TOKEN = env_str("TELEGRAM_BOT_TOKEN_CMTEAM", env_str("TELEGRAM_BOT_TOKEN", "")).strip()
ALLOWED_USER = env_str("TELEGRAM_ALLOWED_USER_ID", "").strip()
COMMAND_NAMESPACE = env_str("TELEGRAM_COMMAND_NAMESPACE", "cm").strip().strip("/")

OFFSET_PATH = WORKSPACE / "telegram_offset.json"
PROCESSED_LOG = WORKSPACE / "processed_updates.log"
LAST_CHAT_ID_PATH = WORKSPACE / "telegram_last_chat_id.json"
FAIL_LOG_PATH = WORKSPACE / "logs" / "executor_failures.jsonl"
FAIL_ALERT_STATE_PATH = WORKSPACE / "executor_failure_alert_state.json"
REVIEW_ALERT_STATE_PATH = WORKSPACE / "review_alert_state.json"
MAX_PROCESSED_IDS = 2000


def load_offset() -> int:
    if not OFFSET_PATH.exists():
        return 0
    try:
        return int(json.loads(OFFSET_PATH.read_text(encoding="utf-8")).get("offset", 0))
    except Exception:
        return 0


def save_offset(offset: int) -> None:
    OFFSET_PATH.write_text(json.dumps({"offset": offset}, indent=2), encoding="utf-8")


def load_processed_ids() -> list[int]:
    lines = [line.strip() for line in read_text(PROCESSED_LOG, "").splitlines() if line.strip()]
    out = []
    for line in lines[-MAX_PROCESSED_IDS:]:
        try:
            out.append(int(line))
        except ValueError:
            continue
    return out


def save_processed_ids(ids: list[int]) -> None:
    bounded = ids[-MAX_PROCESSED_IDS:]
    write_text(PROCESSED_LOG, "\n".join(str(i) for i in bounded) + ("\n" if bounded else ""))


def api(method: str, **kwargs):
    return requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=kwargs, timeout=15).json()


def get_updates(offset: int):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    r = requests.get(url, params={"offset": offset, "timeout": 0}, timeout=15)
    return r.json()


def send(chat_id: int, text: str) -> None:
    text = text[:3900]
    api("sendMessage", chat_id=chat_id, text=text)


def load_last_chat_id() -> int | None:
    if not LAST_CHAT_ID_PATH.exists():
        return None
    try:
        return int(json.loads(LAST_CHAT_ID_PATH.read_text(encoding="utf-8")).get("chat_id"))
    except Exception:
        return None


def save_last_chat_id(chat_id: int) -> None:
    LAST_CHAT_ID_PATH.write_text(json.dumps({"chat_id": chat_id}, indent=2), encoding="utf-8")


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def is_allowed_user(user_id: str) -> bool:
    if not ALLOWED_USER:
        return True
    return user_id == ALLOWED_USER


def command(name: str) -> str:
    if COMMAND_NAMESPACE:
        return f"/{COMMAND_NAMESPACE}_{name}"
    return f"/{name}"


def parse_command(text: str) -> tuple[str, str]:
    text = text.strip()
    if not text.startswith("/"):
        return "", ""
    parts = text.split(maxsplit=1)
    token = parts[0][1:]
    rest = parts[1].strip() if len(parts) > 1 else ""
    prefix = f"{COMMAND_NAMESPACE}_"
    if COMMAND_NAMESPACE and token.startswith(prefix):
        token = token[len(prefix) :]
    return token, rest


def maybe_send_failure_alert() -> None:
    threshold = env_int("EXECUTOR_ALERT_THRESHOLD", 3)
    window_min = env_int("EXECUTOR_ALERT_WINDOW_MINUTES", 15)
    cooldown_min = env_int("EXECUTOR_ALERT_COOLDOWN_MINUTES", 30)
    if threshold <= 0:
        return

    chat_id = load_last_chat_id()
    if chat_id is None or not FAIL_LOG_PATH.exists():
        return

    now = datetime.now().astimezone()
    window_start = now - timedelta(minutes=window_min)
    recent = []
    for line in read_text(FAIL_LOG_PATH, "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            ts = parse_iso(item.get("ts", ""))
        except Exception:
            continue
        if ts >= window_start:
            recent.append(item)

    if len(recent) < threshold:
        return

    state = {}
    if FAIL_ALERT_STATE_PATH.exists():
        try:
            state = json.loads(FAIL_ALERT_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    last_alert_at = state.get("last_alert_at")
    if last_alert_at:
        try:
            if now - parse_iso(last_alert_at) < timedelta(minutes=cooldown_min):
                return
        except Exception:
            pass

    sample = recent[-1]
    msg = (
        f"Executor alert: {len(recent)} failures in the last {window_min}m.\n"
        f"Latest: task={sample.get('task_id', '?')} role={sample.get('role', '?')}\n"
        f"Reason: {str(sample.get('reason', ''))[:300]}"
    )
    send(chat_id, msg)
    FAIL_ALERT_STATE_PATH.write_text(
        json.dumps({"last_alert_at": now.isoformat(), "last_count": len(recent)}, indent=2),
        encoding="utf-8",
    )


def list_awaiting_review_tasks() -> list[dict[str, str]]:
    tasks_root = current_tasks_root(WORKSPACE)
    if not tasks_root.exists():
        return []

    items: list[dict[str, str]] = []
    for task_dir in sorted(tasks_root.iterdir()):
        if not task_dir.is_dir():
            continue
        meta = read_json(task_dir / "meta.json", {})
        if not isinstance(meta, dict):
            continue
        if meta.get("state") != "awaiting_review":
            continue
        items.append(
            {
                "id": str(meta.get("id", task_dir.name.split("_")[0])),
                "role": str(meta.get("role", "")),
                "awaiting_review_at": str(meta.get("awaiting_review_at", "")),
                "review_deadline_at": str(meta.get("review_deadline_at", "")),
            }
        )
    return items


def reviews_text() -> str:
    awaiting = list_awaiting_review_tasks()
    if not awaiting:
        return "No tasks are currently awaiting review."

    lines = ["Tasks awaiting review:"]
    for item in awaiting:
        task_id = item.get("id", "?")
        role = item.get("role", "unknown")
        deadline = item.get("review_deadline_at", "unknown")
        lines.append(f"- {task_id} ({role}) deadline={deadline}")
        lines.append(f"  {command('approve')} {task_id}")
        lines.append(f"  {command('change')} {task_id} <notes>")
        lines.append(f"  {command('block')} {task_id} <notes>")
    return "\n".join(lines)


def maybe_send_review_alerts() -> None:
    chat_id = load_last_chat_id()
    if chat_id is None:
        return

    state = read_json(REVIEW_ALERT_STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}
    notified = state.get("notified", {})
    if not isinstance(notified, dict):
        notified = {}

    awaiting = list_awaiting_review_tasks()
    active_ids = {item["id"] for item in awaiting}

    # Remove stale records for tasks no longer awaiting review.
    for task_id in list(notified.keys()):
        if task_id not in active_ids:
            notified.pop(task_id, None)

    for item in awaiting:
        task_id = item["id"]
        marker = item.get("awaiting_review_at") or item.get("review_deadline_at") or "unknown"
        if notified.get(task_id) == marker:
            continue

        msg = (
            "Marketing Head: review needed.\n"
            f"Task: {task_id} ({item.get('role', 'unknown')})\n"
            f"Decision deadline: {item.get('review_deadline_at', 'unknown')}\n\n"
            "Reply with one of:\n"
            f"- {command('approve')} {task_id}\n"
            f"- {command('change')} {task_id} <notes>\n"
            f"- {command('block')} {task_id} <notes>"
        )
        send(chat_id, msg)
        notified[task_id] = marker

    write_json(REVIEW_ALERT_STATE_PATH, {"notified": notified})


def find_task_dir(task_id: str) -> Path | None:
    # Resolve against current run first to avoid cross-run collisions.
    tasks_root = current_tasks_root(WORKSPACE)
    match = next(tasks_root.glob(f"{task_id}_*"), None)
    if match:
        return match
    return None


def task_show_text(task_dir: Path) -> str:
    meta = read_json(task_dir / "meta.json", {})
    task_id = str(meta.get("id", task_dir.name.split("_")[0]))
    role = str(meta.get("role", "unknown"))
    state = str(meta.get("state", "unknown"))
    deadline = str(meta.get("review_deadline_at", ""))

    result = read_text(task_dir / "result.md", "").strip()
    review = read_text(task_dir / "REVIEW.md", "").strip()

    lines = [f"Task: {task_id} ({role})", f"State: {state}"]
    if deadline:
        lines.append(f"Review deadline: {deadline}")

    if result:
        lines.append("\n# RESULT (truncated)\n")
        lines.append(result[:3000])
    else:
        lines.append("\nNo result yet.")

    if review:
        lines.append("\n# REVIEW\n")
        lines.append(review[:800])

    if state == "awaiting_review":
        lines.append("\nActions:")
        lines.append(f"- {command('approve')} {task_id}")
        lines.append(f"- {command('change')} {task_id} <notes>")
        lines.append(f"- {command('block')} {task_id} <notes>")

    return "\n".join(lines)


def get_current_run_name() -> str:
    return get_current_run_name_from_root(WORKSPACE / "runs")


def list_runs() -> list[str]:
    runs_root = WORKSPACE / "runs"
    if not runs_root.exists():
        return []
    return [d.name for d in sorted(runs_root.iterdir()) if d.is_dir()]


def switch_run(name: str) -> bool:
    d = WORKSPACE / "runs" / name
    if not d.exists() or not d.is_dir():
        return False
    (WORKSPACE / "runs" / "CURRENT_RUN.txt").write_text(name, encoding="utf-8")
    return True


def main() -> None:
    if not BOT_TOKEN:
        return

    maybe_send_failure_alert()
    maybe_send_review_alerts()

    offset = load_offset()
    processed = load_processed_ids()
    processed_set = set(processed)

    data = get_updates(offset)
    for upd in data.get("result", []):
        upd_id = upd.get("update_id")
        if upd_id is None:
            continue

        if upd_id in processed_set:
            continue

        save_offset(upd_id + 1)
        processed.append(upd_id)
        processed_set.add(upd_id)

        msg = upd.get("message") or {}
        user = msg.get("from") or {}
        if not is_allowed_user(str(user.get("id", ""))):
            continue

        chat_id = msg.get("chat", {}).get("id")
        text = (msg.get("text") or "").strip()
        if not chat_id or not text:
            continue
        save_last_chat_id(int(chat_id))
        cmd, rest = parse_command(text)

        if cmd == "new":
            objective = rest.strip()
            if not objective:
                send(chat_id, f"Usage: {command('new')} <objective>")
                continue
            write_text(WORKSPACE / "run_request.md", objective)
            send(chat_id, "New objective received. Pipeline will start shortly.")
            continue

        if cmd == "status":
            run_name = get_current_run_name()
            status_path = WORKSPACE / "runs" / run_name / "status.md"
            send(chat_id, read_text(status_path, "No status yet."))
            continue

        if cmd == "reviews":
            send(chat_id, reviews_text())
            continue

        if cmd == "show":
            tid = rest.strip().split()[0] if rest.strip() else ""
            if not tid:
                send(chat_id, f"Usage: {command('show')} T-0002")
                continue
            d = find_task_dir(tid)
            if not d:
                send(chat_id, f"Task {tid} not found in current run.")
                continue
            send(chat_id, task_show_text(d))
            continue

        if cmd == "health":
            recent = [line for line in read_text(FAIL_LOG_PATH, "").splitlines() if line.strip()]
            send(chat_id, f"Health: executor failure log entries={len(recent)}")
            continue

        if cmd == "runs":
            current = get_current_run_name()
            runs = list_runs()
            if not runs:
                send(chat_id, "No runs found.")
            else:
                lines = [f"Current: {current}", "Runs:"] + [f"- {name}" for name in runs[-20:]]
                send(chat_id, "\n".join(lines))
            continue

        if cmd == "switch":
            if not rest:
                send(chat_id, f"Usage: {command('switch')} <run-id>")
                continue
            run_id = rest.strip()
            if switch_run(run_id):
                send(chat_id, f"Switched current run to {run_id}")
            else:
                send(chat_id, f"Run not found: {run_id}")
            continue

        if cmd == "approve":
            args = rest.split()
            if len(args) < 1:
                send(chat_id, f"Usage: {command('approve')} T-0002")
                continue
            tid = args[0].strip()
            d = find_task_dir(tid)
            if not d:
                send(chat_id, f"Task {tid} not found.")
                continue
            write_text(d / "user_feedback.md", "DECISION: APPROVE\n")
            send(chat_id, f"Approved {tid}")
            continue

        if cmd == "change":
            args = rest.split(maxsplit=1)
            if len(args) < 2:
                send(chat_id, f"Usage: {command('change')} T-0002 <notes>")
                continue
            tid, notes = args[0].strip(), args[1].strip()
            d = find_task_dir(tid)
            if not d:
                send(chat_id, f"Task {tid} not found.")
                continue
            write_text(d / "user_feedback.md", f"DECISION: CHANGES\nNOTES:\n{notes}\n")
            send(chat_id, f"Change request recorded for {tid}")
            continue

        if cmd == "block":
            args = rest.split(maxsplit=1)
            if len(args) < 1:
                send(chat_id, f"Usage: {command('block')} T-0002 <optional notes>")
                continue
            tid = args[0].strip()
            notes = args[1].strip() if len(args) > 1 else ""
            d = find_task_dir(tid)
            if not d:
                send(chat_id, f"Task {tid} not found.")
                continue
            payload = "DECISION: BLOCK\n"
            if notes:
                payload += f"NOTES:\n{notes}\n"
            write_text(d / "user_feedback.md", payload)
            send(chat_id, f"Blocked {tid}")
            continue

        if cmd == "unlock":
            args = rest.split()
            if len(args) < 1:
                send(chat_id, f"Usage: {command('unlock')} T-0002")
                continue
            tid = args[0].strip()
            d = find_task_dir(tid)
            if not d:
                send(chat_id, f"Task {tid} not found.")
                continue
            lock = d / "LOCK"
            if lock.exists():
                lock.unlink()
                send(chat_id, f"Unlocked {tid}")
            else:
                send(chat_id, f"{tid} has no LOCK.")
            continue

        if cmd == "requeue":
            args = rest.split()
            if len(args) < 1:
                send(chat_id, f"Usage: {command('requeue')} T-0002")
                continue
            tid = args[0].strip()
            d = find_task_dir(tid)
            if not d:
                send(chat_id, f"Task {tid} not found.")
                continue
            meta_path = d / "meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            meta["state"] = "queued"
            meta["requeued_by"] = "telegram"
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            lock = d / "LOCK"
            if lock.exists():
                lock.unlink()
            send(chat_id, f"Requeued {tid}")
            continue

        send(
            chat_id,
            "Commands: "
            f"{command('new')} {command('status')} {command('reviews')} {command('show')} {command('health')} "
            f"{command('approve')} {command('change')} {command('block')} "
            f"{command('requeue')} {command('unlock')} {command('runs')} {command('switch')}"
            "\nLegacy unprefixed commands are also accepted.",
        )

    save_processed_ids(processed)
    maybe_send_review_alerts()


if __name__ == "__main__":
    main()
