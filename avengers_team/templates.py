from __future__ import annotations


def handoff_packet_md(
    task_id: str,
    role: str,
    priority: int,
    depends_on: list[str],
    timeout_minutes: int,
    objective: str,
    context_lines: list[str],
    deliverable_lines: list[str],
    acceptance_lines: list[str],
) -> str:
    deps = ", ".join(depends_on) if depends_on else "none"
    context = "\n".join(f"- {line}" for line in context_lines) or "- (none)"
    deliverables = "\n".join(f"- {line}" for line in deliverable_lines) or "- (none)"
    acceptance = "\n".join(f"- {line}" for line in acceptance_lines) or "- (none)"

    return f"""# HANDOFF_PACKET

id: {task_id}
role: {role}
priority: {priority}
depends_on: {deps}
timeout_minutes: {timeout_minutes}

## Objective
{objective}

## Context
{context}

## Deliverables
{deliverables}

## Acceptance Criteria
{acceptance}

# END_PACKET
"""


def review_instructions_md(task_id: str, deadline_iso: str) -> str:
    return f"""# REVIEW INSTRUCTIONS

Task: {task_id}
Decision deadline: {deadline_iso}

Create `user_feedback.md` in this task folder with one of:

- `DECISION: APPROVE`
- `DECISION: CHANGES`
  `NOTES:`
  `<what to change>`
- `DECISION: BLOCK`
  `NOTES:`
  `<why blocked>`

Telegram shortcuts:
- Preferred (namespaced): `/av_approve {task_id}`, `/av_change {task_id} <what to change>`, `/av_block {task_id} <why blocked>`
- Legacy (also accepted): `/approve {task_id}`, `/change {task_id} <what to change>`, `/block {task_id} <why blocked>`

Captain America handoff:
- Orchestrator should prompt the user for one of APPROVE / CHANGES / BLOCK for this task.
"""
