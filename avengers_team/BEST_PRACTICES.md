# BEST_PRACTICES.md - avengers_team Control Plane

## Security
- Keep `OPENCLAW_AVENGERS_GATEWAY_TOKEN` explicit and rotated.
- Use dedicated Telegram bot token for Avengers control plane (`TELEGRAM_BOT_TOKEN_AVENGERS`).
- Restrict command handling with `TELEGRAM_ALLOWED_USER_ID_AVENGERS`.

## Queue Integrity
- Trigger runs only through `/workspace/run_request.md`.
- Preserve all run artifacts under `/workspace/runs/<run-id>`.
- Keep `CURRENT_RUN.txt` authoritative for workers/telegram/orchestrator.

## Orchestration Reliability
- Maintain 3-round advisory flow + final captain synthesis task.
- Block downstream queued tasks when dependencies fail.
- Keep fallback behavior for empty agent payloads to preserve run continuity.

## Output Contract
- Enforce RESULT schema.
- Keep synthesis operator-grade and user-ready.
