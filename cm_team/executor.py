from __future__ import annotations

import os
import subprocess
from pathlib import Path

from cm_team.lib_queue import now_iso_local, read_json, write_text


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def run_executor(role: str, task_md: Path, result_md: Path) -> None:
    mode = env_str("EXECUTOR_MODE", "mock").strip().lower()
    timeout_s = env_int("EXECUTOR_TIMEOUT_SECONDS", 240)

    if mode == "mock":
        task_id = read_json(task_md.parent / "meta.json", {}).get("id", task_md.parent.name)
        write_text(
            result_md,
            f"""# RESULT
id: {task_id}
generated_at: {now_iso_local()}
role: {role}

## Summary
(MOCK) Automated output generated.

## Detailed Output
Placeholder result for role={role}.
Task source: {task_md.name}

## Risks / Unknowns
- Mock output

## Next Questions
- Configure EXECUTOR_MODE=command and set EXECUTOR_COMMAND.
# END_RESULT
""",
        )
        return

    if mode == "command":
        tpl = env_str("EXECUTOR_COMMAND", "").strip()
        if not tpl:
            raise RuntimeError("EXECUTOR_MODE=command but EXECUTOR_COMMAND is empty")

        cmd = tpl.format(ROLE=role, TASK=str(task_md), RESULT=str(result_md))

        try:
            completed = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Executor timed out after {timeout_s}s: {cmd}") from e

        if completed.returncode != 0:
            raise RuntimeError(
                f"Executor failed rc={completed.returncode}\nCMD: {cmd}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )
        return

    raise RuntimeError(f"Unknown EXECUTOR_MODE: {mode}")
