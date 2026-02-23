#!/usr/bin/env bash
set -euo pipefail

mkdir -p /workspace/logs /var/lock/cm_team

ENV_FILE=/workspace/.cm_team_env.sh
{
  echo "#!/usr/bin/env bash"
  for var in \
    WORKSPACE_ROOT \
    PYTHONPATH \
    REVIEW_WINDOW_SECONDS \
    TASK_TIMEOUT_SECONDS \
    TIMEOUT_POLICY \
    EXECUTOR_MODE \
    EXECUTOR_COMMAND \
    EXECUTOR_TIMEOUT_SECONDS \
    MIN_RESULT_BYTES \
    MAX_REVISIONS \
    RUN_POLICY \
    SOUL_ROOT \
    OPENCLAW_CONTAINER \
    OPENCLAW_AGENT_TIMEOUT_SECONDS \
    OPENCLAW_SESSION_MODE \
    OPENCLAW_RESET_AGENT_SESSION \
    OPENCLAW_PREFER_WORKSPACE_RESULT \
    OPENCLAW_AGENT_RESEARCHER \
    OPENCLAW_AGENT_COPYWRITER \
    OPENCLAW_AGENT_QA \
    OPENCLAW_AGENT_HUMANIZER \
    TELEGRAM_BOT_TOKEN_CMTEAM \
    TELEGRAM_BOT_TOKEN \
    TELEGRAM_ALLOWED_USER_ID \
    TELEGRAM_COMMAND_NAMESPACE \
    EXECUTOR_ALERT_THRESHOLD \
    EXECUTOR_ALERT_WINDOW_MINUTES \
    EXECUTOR_ALERT_COOLDOWN_MINUTES
  do
    val="${!var-}"
    printf "export %s=%q\n" "$var" "$val"
  done
} > "$ENV_FILE"
chmod 0600 "$ENV_FILE"

TICK_INTERVAL_SECONDS="${TICK_INTERVAL_SECONDS:-60}"

run_tick() {
  local lock_path="$1"
  local cmd="$2"
  local logfile="$3"
  /bin/bash -lc "source /workspace/.cm_team_env.sh; flock -n ${lock_path} ${cmd}" >> "${logfile}" 2>&1 || true
}

echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') cm_team scheduler started (interval=${TICK_INTERVAL_SECONDS}s)" >> /workspace/logs/orchestrator.tick.log

while true; do
  started_at="$(date +%s)"

  run_tick /var/lock/cm_team/orchestrator.lock "/usr/local/bin/python -m cm_team.orchestrator_tick" /workspace/logs/orchestrator.tick.log &
  run_tick /var/lock/cm_team/researcher.lock "/usr/local/bin/python -m cm_team.worker_tick --role researcher" /workspace/logs/researcher.tick.log &
  run_tick /var/lock/cm_team/copywriter.lock "/usr/local/bin/python -m cm_team.worker_tick --role copywriter" /workspace/logs/copywriter.tick.log &
  run_tick /var/lock/cm_team/qa.lock "/usr/local/bin/python -m cm_team.worker_tick --role qa" /workspace/logs/qa.tick.log &
  run_tick /var/lock/cm_team/humanizer.lock "/usr/local/bin/python -m cm_team.worker_tick --role humanizer" /workspace/logs/humanizer.tick.log &
  run_tick /var/lock/cm_team/telegram.lock "/usr/local/bin/python -m cm_team.telegram_tick" /workspace/logs/telegram.tick.log &

  wait

  finished_at="$(date +%s)"
  elapsed="$((finished_at - started_at))"
  sleep_for="$((TICK_INTERVAL_SECONDS - elapsed))"
  if [ "$sleep_for" -lt 1 ]; then
    sleep_for=1
  fi
  sleep "$sleep_for"
done
