from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from avengers_team.lib_queue import (
    get_current_run_dir,
    lock_remove,
    now_iso_local,
    parse_iso,
    read_json,
    read_text,
    set_current_run_dir,
    task_paths,
    tasks_root_for_run,
    write_json,
    write_text,
)
from avengers_team.templates import handoff_packet_md


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def read_meta(path: Path) -> dict:
    value = read_json(path, {})
    return value if isinstance(value, dict) else {}


def list_tasks(tasks_root: Path) -> list[Path]:
    if not tasks_root.exists():
        return []
    return [d for d in sorted(tasks_root.iterdir()) if d.is_dir()]


ACTIVE_STATES = {"queued", "in_progress", "awaiting_review"}
TERMINAL_FAILURE_STATES = {"failed", "blocked", "stale"}


def has_active_tasks(tasks_root: Path) -> bool:
    for d in list_tasks(tasks_root):
        st = read_meta(d / "meta.json").get("state")
        if st in ACTIVE_STATES:
            return True
    return False


def archive_existing_tasks(workspace: Path, tasks_root: Path) -> None:
    tasks = list_tasks(tasks_root)
    if not tasks:
        return
    archive_dir = tasks_root.parent / "_replaced_tasks" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    archive_dir.mkdir(parents=True, exist_ok=True)
    for d in tasks:
        d.rename(archive_dir / d.name)


def promote_pending_request_if_idle(workspace: Path, tasks_root: Path) -> None:
    req = workspace / "run_request.md"
    if req.exists():
        return
    if has_active_tasks(tasks_root):
        return

    pending_root = workspace / "pending_run_requests"
    files = sorted([p for p in pending_root.glob("*.md") if p.is_file()])
    if not files:
        return

    chosen = files[0]
    body = read_text(chosen, "").strip()
    if body:
        write_text(req, body)
    chosen.unlink(missing_ok=True)


def extract_objective(body: str) -> str:
    for line in body.splitlines():
        s = line.strip()
        if s.lower().startswith("objective:"):
            val = s.split(":", 1)[1].strip()
            if val:
                return val
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        return s
    return body.strip()


def ensure_dirs(workspace: Path) -> None:
    (workspace / "runs").mkdir(parents=True, exist_ok=True)
    (workspace / "logs").mkdir(parents=True, exist_ok=True)
    (workspace / "pending_run_requests").mkdir(parents=True, exist_ok=True)


def heartbeat_stale(task_dir: Path, timeout_seconds: int) -> bool:
    tp = task_paths(task_dir)
    hb = read_json(tp.heartbeat_json, {})
    t = hb.get("last_heartbeat_at")
    if not t:
        return False
    age = (datetime.now().astimezone() - parse_iso(t)).total_seconds()
    return age > timeout_seconds


def mark_stale(task_dir: Path, reason: str) -> None:
    tp = task_paths(task_dir)
    meta = read_meta(tp.meta_json)
    meta["state"] = "stale"
    meta["stale_at"] = now_iso_local()
    meta["stale_reason"] = reason
    write_json(tp.meta_json, meta)


def requeue(task_dir: Path, reason: str) -> None:
    tp = task_paths(task_dir)
    meta = read_meta(tp.meta_json)
    meta["state"] = "queued"
    meta["requeued_at"] = now_iso_local()
    meta["requeue_reason"] = reason
    write_json(tp.meta_json, meta)
    lock_remove(tp.lock)


def parse_feedback(feedback: str) -> tuple[str, str]:
    decision = ""
    notes_lines = []
    for line in feedback.splitlines():
        if line.strip().upper().startswith("DECISION:"):
            decision = line.split(":", 1)[1].strip().upper()
        elif line.strip().upper().startswith("NOTES:"):
            notes_lines.append(line.split(":", 1)[1].strip())
        else:
            if notes_lines and line.strip():
                notes_lines.append(line.strip())
    return decision, "\n".join(notes_lines).strip()


def next_revision_id(base_id: str, revision_count: int) -> str:
    return f"{base_id}R{revision_count}"


def create_task(
    tasks_root: Path,
    task_id: str,
    slug: str,
    role: str,
    priority: int,
    depends_on: list[str],
    objective: str,
    context_lines: list[str],
    deliverable_lines: list[str],
    acceptance_lines: list[str],
) -> None:
    task_dir = tasks_root / f"{task_id}_{slug}"
    if task_dir.exists():
        return

    task_dir.mkdir(parents=True, exist_ok=True)
    task_md = handoff_packet_md(
        task_id=task_id,
        role=role,
        priority=priority,
        depends_on=depends_on,
        timeout_minutes=10,
        objective=objective,
        context_lines=context_lines,
        deliverable_lines=deliverable_lines,
        acceptance_lines=acceptance_lines,
    )
    write_text(task_dir / "task.md", task_md)
    write_json(
        task_dir / "meta.json",
        {
            "id": task_id,
            "slug": slug,
            "role": role,
            "state": "queued",
            "priority": priority,
            "depends_on": depends_on,
            "created_at": now_iso_local(),
            "assigned_by": "orchestrator",
            "revision_count": 0,
        },
    )


def apply_review_gates(tasks_root: Path) -> None:
    now = datetime.now().astimezone()
    max_revisions = env_int("MAX_REVISIONS", 3)

    for d in list_tasks(tasks_root):
        tp = task_paths(d)
        meta = read_meta(tp.meta_json)
        state = meta.get("state")

        if state == "done" and tp.feedback_md.exists():
            feedback = read_text(tp.feedback_md, "").strip()
            decision, notes = parse_feedback(feedback)
            if decision in ("CHANGES", "BLOCK"):
                base_id = meta.get("id", d.name.split("_")[0])
                rev_count = int(meta.get("revision_count", 0)) + 1
                if rev_count > max_revisions:
                    meta["late_feedback_ignored_at"] = now_iso_local()
                    meta["late_feedback_reason"] = "max_revisions_reached"
                    write_json(tp.meta_json, meta)
                else:
                    new_id = next_revision_id(base_id, rev_count)
                    slug = meta.get("slug", "rev") + f"_rev{rev_count}"
                    create_task(
                        tasks_root=tasks_root,
                        task_id=new_id,
                        slug=slug,
                        role=meta.get("role", "captain-america"),
                        priority=int(meta.get("priority", 50)),
                        depends_on=meta.get("depends_on", []),
                        objective=f"REVISION of {base_id}: apply requested changes",
                        context_lines=[
                            "This is a revision task created from late feedback.",
                            f"Original task: {base_id}",
                            "Apply the user's notes below.",
                            notes or "(no notes)",
                        ],
                        deliverable_lines=["Produce updated output in RESULT format."],
                        acceptance_lines=["Incorporates user notes."],
                    )
                    meta["revision_count"] = rev_count
                    meta["late_feedback_created_revision"] = new_id
                    write_json(tp.meta_json, meta)

            try:
                tp.feedback_md.unlink()
            except FileNotFoundError:
                pass
            continue

        if state != "awaiting_review":
            continue

        deadline = meta.get("review_deadline_at")
        deadline_dt = parse_iso(deadline) if deadline else None

        feedback = read_text(tp.feedback_md, "").strip()
        if feedback:
            decision, notes = parse_feedback(feedback)

            if decision == "APPROVE":
                meta["state"] = "done"
                meta["approved_at"] = now_iso_local()
                write_json(tp.meta_json, meta)
                lock_remove(tp.lock)
                try:
                    tp.feedback_md.unlink()
                except FileNotFoundError:
                    pass
                continue

            if decision == "CHANGES":
                rev_count = int(meta.get("revision_count", 0)) + 1
                if rev_count > max_revisions:
                    meta["state"] = "blocked"
                    meta["blocked_at"] = now_iso_local()
                    meta["blocked_notes"] = "max revisions reached"
                    write_json(tp.meta_json, meta)
                else:
                    task_text = read_text(tp.task_md, "")
                    task_text += f"\n\n---\n\n## USER CHANGE REQUEST @ {now_iso_local()}\n{notes or '(no notes)'}\n"
                    write_text(tp.task_md, task_text)

                    meta["state"] = "queued"
                    meta["revised_at"] = now_iso_local()
                    meta["revision_count"] = rev_count
                    write_json(tp.meta_json, meta)
                    lock_remove(tp.lock)

                try:
                    tp.feedback_md.unlink()
                except FileNotFoundError:
                    pass
                continue

            if decision == "BLOCK":
                meta["state"] = "blocked"
                meta["blocked_at"] = now_iso_local()
                meta["blocked_notes"] = notes
                write_json(tp.meta_json, meta)
                try:
                    tp.feedback_md.unlink()
                except FileNotFoundError:
                    pass
                continue

        if deadline_dt and now >= deadline_dt:
            meta["state"] = "done"
            meta["auto_approved_at"] = now_iso_local()
            write_json(tp.meta_json, meta)
            lock_remove(tp.lock)


def block_unrunnable_tasks(tasks_root: Path) -> None:
    task_index: dict[str, Path] = {}
    for d in list_tasks(tasks_root):
        meta = read_meta(d / "meta.json")
        task_id = str(meta.get("id", d.name.split("_")[0]))
        task_index[task_id] = d

    for d in list_tasks(tasks_root):
        tp = task_paths(d)
        meta = read_meta(tp.meta_json)
        if meta.get("state") != "queued":
            continue

        depends_on = meta.get("depends_on", [])
        if not isinstance(depends_on, list) or not depends_on:
            continue

        for dep_id in depends_on:
            dep_dir = task_index.get(str(dep_id))
            if not dep_dir:
                continue
            dep_state = read_meta(dep_dir / "meta.json").get("state")
            if dep_state in TERMINAL_FAILURE_STATES:
                meta["state"] = "blocked"
                meta["blocked_at"] = now_iso_local()
                meta["blocked_notes"] = f"dependency_{dep_id}_state_{dep_state}"
                write_json(tp.meta_json, meta)
                lock_remove(tp.lock)
                break


def reconcile_orphan_locks(tasks_root: Path, timeout_seconds: int, timeout_policy: str) -> None:
    for d in list_tasks(tasks_root):
        tp = task_paths(d)
        meta = read_meta(tp.meta_json)
        st = meta.get("state")

        if st == "queued" and tp.lock.exists():
            hb = read_json(tp.heartbeat_json, {})
            t = hb.get("last_heartbeat_at")
            if not t:
                lock_remove(tp.lock)
                continue
            if heartbeat_stale(d, timeout_seconds):
                lock_remove(tp.lock)
            else:
                mark_stale(d, "queued_but_locked")
            continue

        if st == "in_progress" and heartbeat_stale(d, timeout_seconds):
            if timeout_policy == "auto_requeue":
                requeue(d, "heartbeat_timeout")
            else:
                mark_stale(d, "heartbeat_timeout")
                lock_remove(tp.lock)


def compile_final(tasks_root: Path, run_dir: Path) -> None:
    parts = []
    for d in list_tasks(tasks_root):
        meta = read_meta(d / "meta.json")
        if meta.get("state") != "done":
            continue
        result = read_text(d / "result.md", "")
        parts.append(f"\n\n---\n\n## {meta.get('id')} ({meta.get('role')})\n\n{result}\n")

    out = "# FINAL OUTPUT\n" + "\n".join(parts) if parts else "# FINAL OUTPUT\n\n(No completed results yet.)\n"
    write_text(run_dir / "final.md", out)


def maybe_create_pipeline_from_run_request(workspace: Path, tasks_root: Path, runs_root: Path) -> Path | None:
    req = workspace / "run_request.md"
    if not req.exists():
        return None

    body = read_text(req, "").strip()
    if not body:
        return None

    run_policy = env_str("RUN_POLICY", "queue").strip().lower()
    active = has_active_tasks(tasks_root)
    has_any_tasks = bool(list_tasks(tasks_root))

    if active and run_policy == "reject":
        pending = workspace / "pending_run_requests" / f"rejected_{datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')}.md"
        write_text(pending, body)
        req.unlink()
        return None

    if active and run_policy == "queue":
        pending = workspace / "pending_run_requests" / f"queued_{datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')}.md"
        write_text(pending, body)
        req.unlink()
        return None

    if has_any_tasks:
        archive_existing_tasks(workspace, tasks_root)

    run_name = "run-" + datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir = set_current_run_dir(runs_root, run_name)
    tasks_root = tasks_root_for_run(run_dir)

    objective = extract_objective(body)
    base_context = [
        "Operating model: Captain America is the only user-facing agent.",
        "Run the fixed 3-round advisory protocol: Diverge -> Converge -> Package.",
        "Output style: practical decisions, steps, scripts/templates, metrics, next actions.",
        "Policy: review gate enabled, silence => auto-approve by deadline.",
        f"Objective: {objective}",
        "If critical context is missing, assume defaults and label assumptions.",
    ]

    r1_ids = {
        "alex-hormozi": "T-0101",
        "brian-tracy": "T-0102",
        "april-dunford": "T-0103",
        "russell-brunson": "T-0104",
        "steve-blank": "T-0105",
    }
    for role, task_id in r1_ids.items():
        create_task(
            tasks_root=tasks_root,
            task_id=task_id,
            slug=f"r1_{role}",
            role=role,
            priority=96,
            depends_on=[],
            objective=f"Round 1 (Divergence): Provide independent advisory output for objective: {objective}",
            context_lines=base_context + ["Do not assume alignment with other experts yet."],
            deliverable_lines=[
                "Diagnosis",
                "Recommendation",
                "Artifacts (copy/scripts/templates)",
                "Risks & tests",
                "Assumptions",
            ],
            acceptance_lines=["Independent expert view with a clear recommendation."],
        )

    all_r1 = sorted(r1_ids.values())
    create_task(
        tasks_root=tasks_root,
        task_id="T-0150",
        slug="captain_r1_to_r2_brief",
        role="captain-america",
        priority=91,
        depends_on=all_r1,
        objective=f"Captain Round-Bridge (R1->R2): Analyze all Round 1 expert outputs, identify what stands out, resolve major tensions, and issue concrete Round 2 guidance for each expert for: {objective}",
        context_lines=base_context
        + [
            "You are acting as team leader, not final presenter yet.",
            "Read all Round 1 results and produce explicit instructions expert-by-expert.",
            "Highlight key signals: strongest opportunities, biggest risks, unresolved conflicts, and assumptions to tighten.",
            "Your guidance should shape Round 2, not repeat Round 1.",
        ],
        deliverable_lines=[
            "Cross-expert synthesis of Round 1",
            "What stands out (signal vs noise)",
            "Conflicts/gaps to resolve in Round 2",
            "Targeted Round 2 instruction block for each expert (5 blocks)",
            "Shared constraints and non-negotiables for Round 2",
        ],
        acceptance_lines=["Round 2 experts can directly execute Captain's guidance without ambiguity."],
    )

    r2_ids = {
        "alex-hormozi": "T-0201",
        "brian-tracy": "T-0202",
        "april-dunford": "T-0203",
        "russell-brunson": "T-0204",
        "steve-blank": "T-0205",
    }
    for role, task_id in r2_ids.items():
        create_task(
            tasks_root=tasks_root,
            task_id=task_id,
            slug=f"r2_{role}",
            role=role,
            priority=86,
            depends_on=all_r1 + ["T-0150"],
            objective=f"Round 2 (Convergence): Resolve conflicts/gaps and tighten your recommendation for: {objective}",
            context_lines=base_context
            + [
                "Use all Round 1 outputs to resolve conflicts.",
                "Use Captain Round-Bridge guidance (T-0150) as your direct brief for this round.",
                "Focus on constraints fit: budget, time, channel, assets.",
                "If you deviate from Captain guidance, state the tradeoff explicitly.",
            ],
            deliverable_lines=[
                "Refined recommendation aligned to likely board direction",
                "Updated artifacts",
                "Explicit conflict resolutions",
                "Updated risks & tests",
            ],
            acceptance_lines=["Recommendation is tighter and conflict-aware."],
        )

    all_r2 = sorted(r2_ids.values())
    create_task(
        tasks_root=tasks_root,
        task_id="T-0250",
        slug="captain_r2_to_r3_brief",
        role="captain-america",
        priority=81,
        depends_on=all_r2,
        objective=f"Captain Round-Bridge (R2->R3): Analyze all Round 2 outputs, lock unified direction, and provide packaging instructions for Round 3 experts for: {objective}",
        context_lines=base_context
        + [
            "You are consolidating the board's intelligence before final packaging.",
            "Resolve any remaining contradictions and define one coherent direction.",
            "Issue role-specific packaging instructions so Round 3 outputs integrate cleanly.",
        ],
        deliverable_lines=[
            "Unified direction statement",
            "Final unresolved items and decisions",
            "Targeted Round 3 packaging instruction block for each expert (5 blocks)",
            "Final assumptions and guardrails for Round 3",
        ],
        acceptance_lines=["Round 3 experts are aligned to one direction with clear packaging instructions."],
    )

    r3_ids = {
        "alex-hormozi": "T-0301",
        "brian-tracy": "T-0302",
        "april-dunford": "T-0303",
        "russell-brunson": "T-0304",
        "steve-blank": "T-0305",
    }
    for role, task_id in r3_ids.items():
        create_task(
            tasks_root=tasks_root,
            task_id=task_id,
            slug=f"r3_{role}",
            role=role,
            priority=76,
            depends_on=all_r2 + ["T-0250"],
            objective=f"Round 3 (Packaging): Produce final compressed deliverables aligned to the unified direction for: {objective}",
            context_lines=base_context
            + [
                "Use Captain Round-Bridge guidance (T-0250) as final packaging brief.",
                "This round is packaging-quality and final.",
                "Optimize for integration into Captain America's final synthesis.",
            ],
            deliverable_lines=[
                "Final artifacts",
                "Final assumptions",
                "Final risks + tests",
                "1-2 immediate next actions",
            ],
            acceptance_lines=["Deliverables are concise, final, and execution-ready."],
        )

    create_task(
        tasks_root=tasks_root,
        task_id="T-0401",
        slug="final_captain_synthesis",
        role="captain-america",
        priority=70,
        depends_on=sorted(r3_ids.values()),
        objective=f"Synthesize the advisory board output into one final user-facing plan for: {objective}",
        context_lines=base_context
        + [
            "You are the only user-facing voice.",
            "Synthesize, do not expose internal advisor chatter verbatim.",
        ],
        deliverable_lines=[
            "One-page strategy summary",
            "Chosen direction + tradeoffs",
            "Execution plan (Day 0-2, Day 3-7, Day 8-30)",
            "Copy/scripts/templates",
            "Metrics + checkpoints",
            "Top 3 actions today",
            "Optional: what you need from user",
        ],
        acceptance_lines=["Final output is board-quality and operator-ready."],
    )

    write_text(run_dir / "run_request.md", body)
    req.unlink()
    return run_dir


def main() -> None:
    workspace = Path(env_str("WORKSPACE_ROOT", "/workspace"))
    ensure_dirs(workspace)

    runs_root = workspace / "runs"
    run_dir = get_current_run_dir(runs_root)
    tasks_root = tasks_root_for_run(run_dir)

    timeout_seconds = env_int("TASK_TIMEOUT_SECONDS", 600)
    timeout_policy = env_str("TIMEOUT_POLICY", "mark_stale")

    promote_pending_request_if_idle(workspace, tasks_root)
    new_run_dir = maybe_create_pipeline_from_run_request(workspace, tasks_root, runs_root)
    if new_run_dir is not None:
        run_dir = new_run_dir
        tasks_root = tasks_root_for_run(run_dir)

    reconcile_orphan_locks(tasks_root, timeout_seconds, timeout_policy)
    apply_review_gates(tasks_root)
    block_unrunnable_tasks(tasks_root)
    compile_final(tasks_root, run_dir)

    counts = {
        "queued": 0,
        "in_progress": 0,
        "awaiting_review": 0,
        "done": 0,
        "blocked": 0,
        "stale": 0,
        "failed": 0,
    }
    for d in list_tasks(tasks_root):
        st = read_meta(d / "meta.json").get("state", "unknown")
        if st in counts:
            counts[st] += 1
    write_text(run_dir / "status.md", f"## Status @ {now_iso_local()}\n\n{counts}\n")


if __name__ == "__main__":
    main()
