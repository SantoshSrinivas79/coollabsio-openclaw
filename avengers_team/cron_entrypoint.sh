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

cat >/etc/cron.d/avengers_team <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

* * * * * /bin/bash -lc 'source /workspace/.avengers_team_env.sh; flock -n /var/lock/avengers_team/orchestrator.lock /usr/local/bin/python -m avengers_team.orchestrator_tick' >> /workspace/logs/orchestrator.tick.log 2>&1
* * * * * /bin/bash -lc 'source /workspace/.avengers_team_env.sh; flock -n /var/lock/avengers_team/captain-america.lock /usr/local/bin/python -m avengers_team.worker_tick --role captain-america' >> /workspace/logs/captain-america.tick.log 2>&1
* * * * * /bin/bash -lc 'source /workspace/.avengers_team_env.sh; flock -n /var/lock/avengers_team/alex-hormozi.lock /usr/local/bin/python -m avengers_team.worker_tick --role alex-hormozi' >> /workspace/logs/alex-hormozi.tick.log 2>&1
* * * * * /bin/bash -lc 'source /workspace/.avengers_team_env.sh; flock -n /var/lock/avengers_team/brian-tracy.lock /usr/local/bin/python -m avengers_team.worker_tick --role brian-tracy' >> /workspace/logs/brian-tracy.tick.log 2>&1
* * * * * /bin/bash -lc 'source /workspace/.avengers_team_env.sh; flock -n /var/lock/avengers_team/april-dunford.lock /usr/local/bin/python -m avengers_team.worker_tick --role april-dunford' >> /workspace/logs/april-dunford.tick.log 2>&1
* * * * * /bin/bash -lc 'source /workspace/.avengers_team_env.sh; flock -n /var/lock/avengers_team/russell-brunson.lock /usr/local/bin/python -m avengers_team.worker_tick --role russell-brunson' >> /workspace/logs/russell-brunson.tick.log 2>&1
* * * * * /bin/bash -lc 'source /workspace/.avengers_team_env.sh; flock -n /var/lock/avengers_team/steve-blank.lock /usr/local/bin/python -m avengers_team.worker_tick --role steve-blank' >> /workspace/logs/steve-blank.tick.log 2>&1
* * * * * /bin/bash -lc 'source /workspace/.avengers_team_env.sh; flock -n /var/lock/avengers_team/telegram.lock /usr/local/bin/python -m avengers_team.telegram_tick' >> /workspace/logs/telegram.tick.log 2>&1
CRON

chmod 0644 /etc/cron.d/avengers_team
crontab /etc/cron.d/avengers_team

exec cron -f
