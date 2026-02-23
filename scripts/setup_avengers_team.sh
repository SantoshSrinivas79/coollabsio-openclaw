#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_CONTAINER="${OPENCLAW_CONTAINER:-openclaw-avengers}"
MODEL_ID="${OPENCLAW_AVENGERS_MODEL:-openrouter/moonshotai/kimi-k2.5}"
WORKSPACE_ROOT="${OPENCLAW_AVENGERS_WORKSPACE_ROOT:-data/openclaw_avengers/workspace}"
QUEUE_ROOT="${AVENGERS_QUEUE_ROOT:-data/avengers_team}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker CLI not found" >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$OPENCLAW_CONTAINER"; then
  echo "container not running: $OPENCLAW_CONTAINER" >&2
  exit 1
fi

mkdir -p "$WORKSPACE_ROOT/agents/avengers" "$QUEUE_ROOT/tasks" "$QUEUE_ROOT/runs" "$QUEUE_ROOT/logs" "$QUEUE_ROOT/pending_run_requests"

cp -R avengers/. "$WORKSPACE_ROOT/agents/avengers/"

cat > "$WORKSPACE_ROOT/AGENTS.md" <<'AGENTS'
# AGENTS: Avengers Advisory Board

## Commander
- captain-america: only user-facing orchestrator.

## Internal Advisors
- alex-hormozi: offers, pricing, guarantees.
- brian-tracy: sales execution and scripts.
- april-dunford: positioning and messaging.
- russell-brunson: funnels and nurture flow.
- steve-blank: hypotheses, discovery, validation.

## Operating rules
- User interacts only with captain-america.
- Captain America delegates and synthesizes all expert inputs.
- For asynchronous multi-stage runs, use:
  `/data/workspace/avengers_run_request.sh "<objective>"`.
- Read outputs from `/data/avengers_team/runs/<run-id>/status.md` and `final.md`.
AGENTS

cat > "$WORKSPACE_ROOT/avengers_run_request.sh" <<'RUNNER'
#!/usr/bin/env bash
set -euo pipefail

OBJECTIVE="${*:-}"
if [ -z "${OBJECTIVE// }" ]; then
  echo "usage: avengers_run_request.sh <objective>" >&2
  exit 2
fi

OUT="/data/avengers_team/run_request.md"
TMP="${OUT}.tmp.$$"

mkdir -p /data/avengers_team
printf "%s\n" "$OBJECTIVE" > "$TMP"
mv "$TMP" "$OUT"

echo "queued: $OUT"
RUNNER
chmod +x "$WORKSPACE_ROOT/avengers_run_request.sh"

existing_json="$(docker exec "$OPENCLAW_CONTAINER" openclaw agents list --json)"
agent_exists() {
  local target="$1"
  AGENTS_JSON="$existing_json" python3 - "$target" <<'PY'
import json
import os
import sys
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

add_agent_if_missing "captain-america" "/data/workspace/agents/avengers/agents/captain-america"
add_agent_if_missing "alex-hormozi" "/data/workspace/agents/avengers/agents/alex-hormozi"
add_agent_if_missing "brian-tracy" "/data/workspace/agents/avengers/agents/brian-tracy"
add_agent_if_missing "april-dunford" "/data/workspace/agents/avengers/agents/april-dunford"
add_agent_if_missing "russell-brunson" "/data/workspace/agents/avengers/agents/russell-brunson"
add_agent_if_missing "steve-blank" "/data/workspace/agents/avengers/agents/steve-blank"

docker exec "$OPENCLAW_CONTAINER" openclaw agents set-identity --agent captain-america --name "Captain America" --emoji "CA" >/dev/null || true
docker exec "$OPENCLAW_CONTAINER" openclaw agents set-identity --agent alex-hormozi --name "Alex Hormozi" --emoji "AH" >/dev/null || true
docker exec "$OPENCLAW_CONTAINER" openclaw agents set-identity --agent brian-tracy --name "Brian Tracy" --emoji "BT" >/dev/null || true
docker exec "$OPENCLAW_CONTAINER" openclaw agents set-identity --agent april-dunford --name "April Dunford" --emoji "AD" >/dev/null || true
docker exec "$OPENCLAW_CONTAINER" openclaw agents set-identity --agent russell-brunson --name "Russell Brunson" --emoji "RB" >/dev/null || true
docker exec "$OPENCLAW_CONTAINER" openclaw agents set-identity --agent steve-blank --name "Steve Blank" --emoji "SB" >/dev/null || true

docker exec "$OPENCLAW_CONTAINER" openclaw agents list --json
