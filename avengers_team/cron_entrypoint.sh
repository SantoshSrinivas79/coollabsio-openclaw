#!/usr/bin/env bash
set -euo pipefail

mkdir -p /workspace/logs /var/lock/avengers_team

ENV_FILE=/workspace/.avengers_team_env.sh
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
    OPENCLAW_AGENT_WORKSPACE_PATH \
    OPENCLAW_AGENT_CAPTAIN_AMERICA \
    OPENCLAW_AGENT_ALEX_HORMOZI \
    OPENCLAW_AGENT_BRIAN_TRACY \
    OPENCLAW_AGENT_APRIL_DUNFORD \
    OPENCLAW_AGENT_RUSSELL_BRUNSON \
    OPENCLAW_AGENT_STEVE_BLANK \
    TELEGRAM_BOT_TOKEN_AVENGERS \
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
  /bin/bash -lc "source /workspace/.avengers_team_env.sh; flock -n ${lock_path} ${cmd}" >> "${logfile}" 2>&1 || true
}

echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') avengers_team scheduler started (interval=${TICK_INTERVAL_SECONDS}s)" >> /workspace/logs/orchestrator.tick.log

while true; do
  started_at="$(date +%s)"

  run_tick /var/lock/avengers_team/orchestrator.lock "/usr/local/bin/python -m avengers_team.orchestrator_tick" /workspace/logs/orchestrator.tick.log &
  run_tick /var/lock/avengers_team/captain-america.lock "/usr/local/bin/python -m avengers_team.worker_tick --role captain-america" /workspace/logs/captain-america.tick.log &
  run_tick /var/lock/avengers_team/alex-hormozi.lock "/usr/local/bin/python -m avengers_team.worker_tick --role alex-hormozi" /workspace/logs/alex-hormozi.tick.log &
  run_tick /var/lock/avengers_team/brian-tracy.lock "/usr/local/bin/python -m avengers_team.worker_tick --role brian-tracy" /workspace/logs/brian-tracy.tick.log &
  run_tick /var/lock/avengers_team/april-dunford.lock "/usr/local/bin/python -m avengers_team.worker_tick --role april-dunford" /workspace/logs/april-dunford.tick.log &
  run_tick /var/lock/avengers_team/russell-brunson.lock "/usr/local/bin/python -m avengers_team.worker_tick --role russell-brunson" /workspace/logs/russell-brunson.tick.log &
  run_tick /var/lock/avengers_team/steve-blank.lock "/usr/local/bin/python -m avengers_team.worker_tick --role steve-blank" /workspace/logs/steve-blank.tick.log &
  run_tick /var/lock/avengers_team/telegram.lock "/usr/local/bin/python -m avengers_team.telegram_tick" /workspace/logs/telegram.tick.log &

  wait

  finished_at="$(date +%s)"
  elapsed="$((finished_at - started_at))"
  sleep_for="$((TICK_INTERVAL_SECONDS - elapsed))"
  if [ "$sleep_for" -lt 1 ]; then
    sleep_for=1
  fi
  sleep "$sleep_for"
done
