#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass
class Entry:
    ts: datetime
    agent_id: str
    session_id: str
    role: str
    text: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build daily Mentor memory markdown from session logs")
    p.add_argument("--sessions-root", default="/mentor_data/.openclaw/agents")
    p.add_argument(
        "--agents",
        nargs="*",
        default=["main", "mentor"],
        help="Agent IDs to include in rollup. Default: main mentor",
    )
    p.add_argument("--memory-dir", default="/mentor_data/workspace/memory")
    p.add_argument("--timezone", default=os.getenv("MENTOR_MEMORY_TIMEZONE", "UTC"))
    p.add_argument("--date", default=None, help="Target date YYYY-MM-DD in selected timezone; default=today")
    return p.parse_args()


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def extract_text(content: list[dict]) -> str:
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        if t == "text" and isinstance(item.get("text"), str):
            parts.append(item["text"])
        elif t in {"input_text", "output_text"} and isinstance(item.get("text"), str):
            parts.append(item["text"])
        elif isinstance(item.get("text"), dict) and isinstance(item["text"].get("value"), str):
            parts.append(item["text"]["value"])
    return "\n".join(parts).strip()


def normalize_message_text(role: str, text: str) -> str:
    t = text.strip()

    # Drop OpenClaw bootstrap chatter from /new or /reset.
    if role == "assistant" and t.startswith("✅ New session started"):
        return ""
    if role == "user" and t.startswith("A new session was started via /new or /reset."):
        return ""

    # Telegram wrapper appears as:
    # Conversation info (untrusted metadata): ... then the actual user text.
    if role == "user" and t.startswith("Conversation info (untrusted metadata):"):
        t = re.sub(
            r"^Conversation info \(untrusted metadata\):\s*```json\s*.*?```\s*",
            "",
            t,
            flags=re.DOTALL,
        ).strip()

    return t


def load_entries(
    sessions_root: Path, agents: list[str], target_date: str, tz: ZoneInfo
) -> tuple[list[Entry], set[str]]:
    entries: list[Entry] = []
    sessions_seen: set[str] = set()

    for agent_id in agents:
        sessions_dir = sessions_root / agent_id / "sessions"
        if not sessions_dir.is_dir():
            continue
        for session_file in sorted(sessions_dir.glob("*.jsonl")):
            sid = session_file.stem
            sessions_seen.add(f"{agent_id}:{sid}")
            with session_file.open("r", encoding="utf-8") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    if obj.get("type") != "message":
                        continue

                    msg = obj.get("message") or {}
                    role = str(msg.get("role") or "unknown")
                    if role not in {"user", "assistant", "system"}:
                        continue

                    ts_val = obj.get("timestamp")
                    ts_dt: datetime | None = None
                    if isinstance(ts_val, str):
                        try:
                            ts_dt = parse_iso(ts_val)
                        except Exception:
                            ts_dt = None
                    if ts_dt is None and isinstance(msg.get("timestamp"), int):
                        ts_dt = datetime.fromtimestamp(msg["timestamp"] / 1000.0, tz=timezone.utc)
                    if ts_dt is None:
                        continue

                    local_day = ts_dt.astimezone(tz).date().isoformat()
                    if local_day != target_date:
                        continue

                    content = msg.get("content") or []
                    if not isinstance(content, list):
                        continue
                    text = extract_text(content)
                    text = normalize_message_text(role, text)
                    if not text:
                        continue

                    entries.append(Entry(ts=ts_dt, agent_id=agent_id, session_id=sid, role=role, text=text))

    entries.sort(key=lambda e: e.ts)
    return entries, sessions_seen


def render_markdown(
    target_date: str, tz: ZoneInfo, entries: list[Entry], scanned_sessions: int, agents: list[str]
) -> str:
    now_local = datetime.now(timezone.utc).astimezone(tz)

    lines: list[str] = []
    lines.append(f"# Mentor Memory Log - {target_date}")
    lines.append("")
    lines.append("Auto-generated daily log for QMD retrieval. Do not edit this file manually.")
    lines.append("")
    lines.append("## Metadata")
    lines.append(f"- Generated at: {now_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    lines.append(f"- Timezone: {tz.key}")
    lines.append(f"- Agents included: {', '.join(agents)}")
    lines.append(f"- Sessions scanned: {scanned_sessions}")
    lines.append(f"- Message entries captured: {len(entries)}")
    lines.append("")

    lines.append("## Daily Composition + Updates")
    if not entries:
        lines.append("- No messages recorded for this date yet.")
        lines.append("")
        return "\n".join(lines) + "\n"

    for i, entry in enumerate(entries, start=1):
        stamp = entry.ts.astimezone(tz).strftime("%H:%M:%S")
        lines.append(
            f"### {i}. {stamp} [{entry.role}] (agent: {entry.agent_id}, session: {entry.session_id})"
        )
        lines.append("")
        lines.append(entry.text)
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()

    try:
        tz = ZoneInfo(args.timezone)
    except Exception:
        tz = ZoneInfo("UTC")

    if args.date:
        target_date = args.date
    else:
        target_date = datetime.now(timezone.utc).astimezone(tz).date().isoformat()

    sessions_root = Path(args.sessions_root)
    memory_dir = Path(args.memory_dir)
    memory_dir.mkdir(parents=True, exist_ok=True)

    entries, sessions_seen = load_entries(sessions_root, args.agents, target_date, tz)
    content = render_markdown(target_date, tz, entries, len(sessions_seen), args.agents)

    out_file = memory_dir / f"{target_date}.md"
    out_file.write_text(content, encoding="utf-8")

    print(f"wrote {out_file} ({len(entries)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
