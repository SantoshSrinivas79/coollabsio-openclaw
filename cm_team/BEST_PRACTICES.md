# BEST_PRACTICES.md - cm_team Control Plane

## Security
- Keep `OPENCLAW_GATEWAY_TOKEN` explicit and secret.
- Use separate Telegram token for review plane when possible (`TELEGRAM_BOT_TOKEN_CMTEAM`).
- Restrict review commands with `TELEGRAM_ALLOWED_USER_ID`.

## Queue Integrity
- Accept new work via `/workspace/run_request.md` or pending queue promotion only.
- Preserve run history under `/workspace/runs/<run-id>`.
- Avoid manual edits to historical artifacts except debugging.

## Execution Reliability
- Prefer isolated agent sessions (`OPENCLAW_SESSION_MODE=isolated`).
- Use review gates for controlled progression.
- Handle failed dependencies explicitly to avoid deadlocks.

## Output Contract
- Enforce RESULT schema and minimum result quality.
- Require practical, actionable outputs.
