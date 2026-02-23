# Contracts: Task / Result / Review

These contracts are mandatory.

---

## Task Contract (HANDOFF_PACKET)

A task is defined by `task.md` and `meta.json`.

`task.md` MUST contain:

- id: <task id>
- role: <researcher|copywriter|qa|humanizer>
- objective
- context (brand voice, audience, channel, constraints)
- deliverable list
- acceptance criteria list

Task must end with:
# END_PACKET

---

## Result Contract (RESULT)

A specialist output MUST be written to `result.md` and MUST contain:

# RESULT
id: <same as task id>

## Summary
(3-6 bullets)

## Detailed Output
(the deliverable)

## Risks / Unknowns
(list)

## Next Questions
(list)

# END_RESULT

Rules:
- No hallucinated facts. If uncertain, label as VERIFY.
- If asked for citations: include links or mark VERIFY if not possible.
- Keep voice consistent with brand voice.
- End with an explicit orchestrator handoff note:
  - "Marketing Head: please request APPROVE / CHANGES / BLOCK from the user for <task id>."

---

## Review Contract (user_feedback.md)

Optional file. If present, MUST contain:

DECISION: APPROVE | CHANGES | BLOCK
NOTES:
<freeform notes>

Rules:
- Silence means AUTO-APPROVE after REVIEW_WINDOW_SECONDS.
- CHANGES triggers requeue of the same task (until MAX_REVISIONS).
- Late CHANGES after task is done creates a revision task (T-XXXXR1...).
- When a task enters `awaiting_review`, the orchestrator must notify the user with exact command options:
  - `/approve <task-id>`
  - `/change <task-id> <notes>`
  - `/block <task-id> <notes>`

---

## State Machine

queued -> in_progress -> awaiting_review -> done
         |                    |
         |                    +-> blocked (on DECISION: BLOCK)
         |
         +-> failed (executor/validation error)
         +-> stale  (timeout / orphaned lock)

---

## Safety / Quality Policies

- Avoid legal/medical/financial guarantees.
- Avoid unverifiable claims.
- Prefer specific examples, clear structure, and concise writing.
- Do not add new factual claims during Humanize step.
