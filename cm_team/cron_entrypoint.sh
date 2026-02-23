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

cat >/etc/cron.d/cm_team <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

* * * * * /bin/bash -lc 'source /workspace/.cm_team_env.sh; flock -n /var/lock/cm_team/orchestrator.lock /usr/local/bin/python -m cm_team.orchestrator_tick' >> /workspace/logs/orchestrator.tick.log 2>&1
* * * * * /bin/bash -lc 'source /workspace/.cm_team_env.sh; flock -n /var/lock/cm_team/researcher.lock /usr/local/bin/python -m cm_team.worker_tick --role researcher' >> /workspace/logs/researcher.tick.log 2>&1
* * * * * /bin/bash -lc 'source /workspace/.cm_team_env.sh; flock -n /var/lock/cm_team/copywriter.lock /usr/local/bin/python -m cm_team.worker_tick --role copywriter' >> /workspace/logs/copywriter.tick.log 2>&1
* * * * * /bin/bash -lc 'source /workspace/.cm_team_env.sh; flock -n /var/lock/cm_team/qa.lock /usr/local/bin/python -m cm_team.worker_tick --role qa' >> /workspace/logs/qa.tick.log 2>&1
* * * * * /bin/bash -lc 'source /workspace/.cm_team_env.sh; flock -n /var/lock/cm_team/humanizer.lock /usr/local/bin/python -m cm_team.worker_tick --role humanizer' >> /workspace/logs/humanizer.tick.log 2>&1
* * * * * /bin/bash -lc 'source /workspace/.cm_team_env.sh; flock -n /var/lock/cm_team/telegram.lock /usr/local/bin/python -m cm_team.telegram_tick' >> /workspace/logs/telegram.tick.log 2>&1
CRON

chmod 0644 /etc/cron.d/cm_team
crontab /etc/cron.d/cm_team

exec cron -f
