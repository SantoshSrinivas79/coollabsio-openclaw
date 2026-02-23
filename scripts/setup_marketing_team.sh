#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_CONTAINER="${OPENCLAW_CONTAINER:-openclaw}"
MODEL_ID="${OPENCLAW_MARKETING_MODEL:-openrouter/moonshotai/kimi-k2.5}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker CLI not found" >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$OPENCLAW_CONTAINER"; then
  echo "container not running: $OPENCLAW_CONTAINER" >&2
  exit 1
fi

mkdir -p data/openclaw/workspace/agents/cm
mkdir -p data/cm_team/tasks data/cm_team/runs data/cm_team/logs data/cm_team/pending_run_requests

make_workspace() {
  local agent_id="$1"
  local soul_file="$2"
  local identity_name="$3"
  local emoji="$4"

  local dir="data/openclaw/workspace/agents/cm/${agent_id}"
  mkdir -p "$dir"

  cp "$soul_file" "$dir/SOUL.md"

  cat >"$dir/IDENTITY.md" <<EOF
# IDENTITY

name: ${identity_name}
emoji: ${emoji}
role: ${agent_id}
EOF

  cat >"$dir/TOOLS.md" <<'EOF'
# TOOLS

- Use concise outputs for orchestration updates.
- When coordinating specialists, call:
  `openclaw agent --agent <specialist-id> --message "..." --json`
- Use `/data/cm_team` for cron pipeline integration:
  - Create `/data/cm_team/run_request.md` to start a new run.
  - Read `/data/cm_team/runs/CURRENT_RUN.txt` for active run.
  - Read `/data/cm_team/runs/<run>/status.md` and `final.md` for progress/output.
EOF

  cat >"$dir/AGENTS.md" <<'EOF'
# Marketing Team Agents

- marketing-head
- researcher
- copywriter
- qa
- humanizer
EOF
}

make_workspace "marketing-head" "cm_soul/01_marketing_head.md" "Marketing Head" "MH"
make_workspace "researcher" "cm_soul/02_researcher.md" "Research Specialist" "R"
make_workspace "copywriter" "cm_soul/03_copywriter.md" "Copywriter" "CW"
make_workspace "qa" "cm_soul/04_qa_reviewer.md" "QA Reviewer" "QA"
make_workspace "humanizer" "cm_soul/05_humanizer.md" "Humanizer" "H"

cat > data/openclaw/workspace/agents/cm/marketing-head/AGENTS.md <<'EOF'
# Marketing Head Orchestration

Primary role: collaborate with the user and orchestrate specialist agents.

## Interaction policy
- Talk to user directly in Telegram/webchat.
- For work execution, delegate to specialist agents: researcher, copywriter, qa, humanizer.
- When user asks to run full pipeline, write objective to `/data/cm_team/run_request.md`.

## Delegation examples
- `openclaw agent --agent researcher --message "<research brief>" --json`
- `openclaw agent --agent copywriter --message "<draft brief>" --json`
- `openclaw agent --agent qa --message "<qa brief>" --json`
- `openclaw agent --agent humanizer --message "<humanize brief>" --json`
EOF

existing_json="$(docker exec "$OPENCLAW_CONTAINER" openclaw agents list --json)"
agent_exists() {
  local target="$1"
  AGENTS_JSON="$existing_json" python3 - "$target" <<'PY'
import json, sys
import os
needle = sys.argv[1]
items = json.loads(os.environ.get("AGENTS_JSON", "[]"))
print("yes" if any((x or {}).get("id") == needle for x in items) else "no")
PY
}

add_agent_if_missing() {
  local id="$1"
  local workspace_path="$2"
  local bind_channel="${3:-}"

  if [ "$(agent_exists "$id")" = "yes" ]; then
    echo "agent exists: $id"
    return
  fi

  cmd=(docker exec "$OPENCLAW_CONTAINER" openclaw agents add "$id" --non-interactive --workspace "$workspace_path" --model "$MODEL_ID")
  if [ -n "$bind_channel" ]; then
    cmd+=(--bind "$bind_channel")
  fi

  "${cmd[@]}"
  echo "agent added: $id"
}

add_agent_if_missing "marketing-head" "/data/workspace/agents/cm/marketing-head"
add_agent_if_missing "researcher" "/data/workspace/agents/cm/researcher"
add_agent_if_missing "copywriter" "/data/workspace/agents/cm/copywriter"
add_agent_if_missing "qa" "/data/workspace/agents/cm/qa"
add_agent_if_missing "humanizer" "/data/workspace/agents/cm/humanizer"

docker exec "$OPENCLAW_CONTAINER" openclaw agents set-identity --agent marketing-head --name "Marketing Head" --emoji "MH" >/dev/null || true
docker exec "$OPENCLAW_CONTAINER" openclaw agents set-identity --agent researcher --name "Research Specialist" --emoji "R" >/dev/null || true
docker exec "$OPENCLAW_CONTAINER" openclaw agents set-identity --agent copywriter --name "Copywriter" --emoji "CW" >/dev/null || true
docker exec "$OPENCLAW_CONTAINER" openclaw agents set-identity --agent qa --name "QA Reviewer" --emoji "QA" >/dev/null || true
docker exec "$OPENCLAW_CONTAINER" openclaw agents set-identity --agent humanizer --name "Humanizer" --emoji "H" >/dev/null || true

docker exec "$OPENCLAW_CONTAINER" openclaw agents list --json
