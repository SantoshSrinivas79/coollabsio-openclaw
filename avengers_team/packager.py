from __future__ import annotations

import os
from pathlib import Path

from avengers_team.lib_queue import read_json, read_text, write_text


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def role_soul_filename(role: str) -> str:
    mapping = {
        "captain-america": "01_captain_america.md",
        "alex-hormozi": "02_alex_hormozi.md",
        "brian-tracy": "03_brian_tracy.md",
        "april-dunford": "04_april_dunford.md",
        "russell-brunson": "05_russell_brunson.md",
        "steve-blank": "06_steve_blank.md",
    }
    if role not in mapping:
        raise RuntimeError(f"Unknown role for soul mapping: {role}")
    return mapping[role]


def build_exec_packet(workspace: Path, task_dir: Path) -> Path:
    soul_root = Path(env_str("SOUL_ROOT", "/soul"))

    meta = read_json(task_dir / "meta.json", {})
    role = meta.get("role", "")
    depends_on = meta.get("depends_on", [])
    if not role:
        raise RuntimeError("Task meta missing role")

    contracts = read_text(soul_root / "00_contracts.md", "")
    role_soul = read_text(soul_root / role_soul_filename(role), "")
    task_md = read_text(task_dir / "task.md", "")

    if not contracts.strip():
        raise RuntimeError(f"Missing/empty contracts file: {soul_root / '00_contracts.md'}")
    if not role_soul.strip():
        raise RuntimeError(f"Missing/empty role soul file: {soul_root / role_soul_filename(role)}")
    if not task_md.strip():
        raise RuntimeError(f"Missing/empty task file: {task_dir / 'task.md'}")

    deps_text = []
    tasks_root = task_dir.parent
    for dep_id in depends_on:
        dep_dir = next(tasks_root.glob(f"{dep_id}_*/"), None)
        if not dep_dir:
            continue
        dep_result = read_text(dep_dir / "result.md", "")
        deps_text.append(f"\n\n---\n\n# DEPENDENCY RESULT: {dep_id}\n\n{dep_result}\n")

    exec_md = f"""# EXECUTION_PACKET
role: {role}

---

# CONTRACTS
{contracts}

---

# ROLE SOUL
{role_soul}

---

# TASK
{task_md}

---

# DEPENDENCIES
{''.join(deps_text) if deps_text else '(none)'}

---

# OUTPUT RULES (STRICT)
- Return ONLY final markdown content following the RESULT contract.
- Do NOT describe what you are about to do.
- Do NOT include progress narration (examples: "Let me check...", "I see...", "Task complete...").
- Do NOT include tool logs, file-save confirmations, or process notes.
- If you cannot complete the task, still return RESULT contract with concrete blockers in Risks / Unknowns.
# END_EXECUTION_PACKET
"""
    out = task_dir / "exec.md"
    write_text(out, exec_md)
    return out
