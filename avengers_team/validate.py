from __future__ import annotations

import os
import re
from pathlib import Path


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def validate_result(result_md: Path) -> None:
    min_bytes = env_int("MIN_RESULT_BYTES", 200)
    if not result_md.exists():
        raise RuntimeError("result.md missing")

    data = result_md.read_text(encoding="utf-8", errors="replace")
    if len(data.encode("utf-8")) < min_bytes:
        raise RuntimeError(f"result.md too small (<{min_bytes} bytes)")

    if "# RESULT" not in data:
        raise RuntimeError("result.md missing '# RESULT' header")
    if "# END_RESULT" not in data:
        raise RuntimeError("result.md missing '# END_RESULT' footer")
    if "\nid:" not in data and not data.startswith("id:"):
        raise RuntimeError("result.md missing required 'id:' field")
    if "## Summary" not in data or "## Detailed Output" not in data:
        raise RuntimeError("result.md missing required sections")

    # Reject process-narration outputs that describe actions instead of deliverables.
    lines = [ln.strip().lower() for ln in data.splitlines() if ln.strip()]
    chatter_patterns = (
        r"^(let me|i see|i'll|i will|i have|task complete|task completed|now i have|checking)\b",
    )
    for ln in lines[:60]:
        if any(re.match(p, ln) for p in chatter_patterns):
            raise RuntimeError("result.md contains process narration, not final deliverable")
