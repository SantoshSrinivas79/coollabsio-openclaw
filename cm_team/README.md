# CM Team + OpenClaw Integration

This repository is configured so `cm_team` executes specialist tasks by calling OpenClaw agents inside the `openclaw` container.

## Runtime bridge

- Executor mode: `command`
- Command: `/app/cm_team/openclaw_exec.sh {ROLE} "{TASK}" "{RESULT}"`
- Transport: Docker socket + `docker exec openclaw openclaw agent --agent <id> --json`
- Session isolation: `OPENCLAW_SESSION_MODE=isolated` and `OPENCLAW_RESET_AGENT_SESSION=1` (default) to prevent cross-task memory bleed
- Artifact preference: `OPENCLAW_PREFER_WORKSPACE_RESULT=1` (default) to use each agent's run artifact (`/data/workspace/agents/cm/<agent>/result.md`) instead of chatty CLI summaries

## Agent bootstrap

Run once (or rerun safely):

```bash
./scripts/setup_marketing_team.sh
```

This creates/updates agents:

- `marketing-head`
- `researcher`
- `copywriter`
- `qa`
- `humanizer`

It also syncs workspace souls under:

- `data/openclaw/workspace/agents/cm/*`

## User-facing orchestrator

The default `main` workspace (`data/openclaw/workspace/`) is set to Marketing Head behavior so Telegram/webchat conversations are user-facing orchestration.

## Shared data path

`openclaw` and `cm_team` both mount `./data/cm_team`:

- OpenClaw path: `/data/cm_team`
- cm_team path: `/workspace`

This enables Marketing Head to trigger runs by writing:

- `/data/cm_team/run_request.md`
- Preferred helper: `/data/workspace/cm_run_request.sh "<objective>"`

## Run-local task storage

Tasks are now isolated per run:

- `data/cm_team/runs/<run-id>/tasks/T-0001_*`
- `data/cm_team/runs/<run-id>/tasks/T-0002_*`
- `data/cm_team/runs/<run-id>/tasks/T-0003_*`
- `data/cm_team/runs/<run-id>/tasks/T-0004_*`

`CURRENT_RUN.txt` determines which run workers/orchestrator/Telegram operate on.
This prevents cross-run task collisions and preserves task history with each run.

## Start/restart

```bash
docker compose up -d --build openclaw cm_team
```

If you edit wrapper/env integration only, a fast restart is enough:

```bash
docker compose restart cm_team
```

## Best Practices
- See `BEST_PRACTICES.md` for security, queue, execution, and output standards.
