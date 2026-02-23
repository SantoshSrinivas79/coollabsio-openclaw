#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:?role required}"
IN_FILE="${2:?input file required}"
OUT_FILE="${3:?output file required}"

OPENCLAW_CONTAINER="${OPENCLAW_CONTAINER:-openclaw}"
OPENCLAW_TIMEOUT_SECONDS="${OPENCLAW_AGENT_TIMEOUT_SECONDS:-600}"
OPENCLAW_RETRY_MAX="${OPENCLAW_EXEC_RETRY_MAX:-3}"
OPENCLAW_RETRY_DELAY_SECONDS="${OPENCLAW_EXEC_RETRY_DELAY_SECONDS:-4}"
OPENCLAW_SESSION_MODE="${OPENCLAW_SESSION_MODE:-isolated}"
OPENCLAW_RESET_AGENT_SESSION="${OPENCLAW_RESET_AGENT_SESSION:-1}"
OPENCLAW_PREFER_WORKSPACE_RESULT="${OPENCLAW_PREFER_WORKSPACE_RESULT:-1}"

case "$ROLE" in
  researcher) AGENT_ID="${OPENCLAW_AGENT_RESEARCHER:-researcher}" ;;
  copywriter) AGENT_ID="${OPENCLAW_AGENT_COPYWRITER:-copywriter}" ;;
  qa) AGENT_ID="${OPENCLAW_AGENT_QA:-qa}" ;;
  humanizer) AGENT_ID="${OPENCLAW_AGENT_HUMANIZER:-humanizer}" ;;
  *) AGENT_ID="$ROLE" ;;
esac

if ! command -v docker >/dev/null 2>&1; then
  echo "docker CLI not found in cm_team container" >&2
  exit 2
fi

if [ ! -S /var/run/docker.sock ]; then
  echo "docker socket not available at /var/run/docker.sock" >&2
  exit 2
fi

if [ ! -f "$IN_FILE" ]; then
  echo "input file not found: $IN_FILE" >&2
  exit 2
fi

PROMPT_CONTENT="$(cat "$IN_FILE")"
TMP_JSON="$(mktemp)"
TMP_ERR="$(mktemp)"
TMP_WS_RESULT="$(mktemp)"
trap 'rm -f "$TMP_JSON" "$TMP_ERR" "$TMP_WS_RESULT"' EXIT

SESSION_ARG=()
if [ "$OPENCLAW_SESSION_MODE" != "shared" ]; then
  TASK_BASENAME="$(basename "$(dirname "$IN_FILE")")"
  SESSION_RAW="cm-${ROLE}-${TASK_BASENAME}-$(date +%s)-$$"
  SESSION_ID="$(printf "%s" "$SESSION_RAW" | tr -cs 'A-Za-z0-9._-' '-')"
  SESSION_ARG=(--session-id "$SESSION_ID")
fi

if [ "$OPENCLAW_SESSION_MODE" != "shared" ] && [ "$OPENCLAW_RESET_AGENT_SESSION" = "1" ]; then
  # OpenClaw may still route agent calls to agent:<role>:main despite --session-id.
  # Clear agent session state before each task to prevent cross-task memory bleed.
  docker exec -e OC_AGENT_ID="$AGENT_ID" "$OPENCLAW_CONTAINER" sh -lc '
    base="/data/.openclaw/agents/$OC_AGENT_ID/sessions"
    if [ -d "$base" ]; then
      find "$base" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
    fi
  ' >/dev/null 2>&1 || true
fi

attempt=1
while :; do
  set +e
  docker exec -i "$OPENCLAW_CONTAINER" \
    openclaw agent \
    --agent "$AGENT_ID" \
    "${SESSION_ARG[@]}" \
    --message "$PROMPT_CONTENT" \
    --timeout "$OPENCLAW_TIMEOUT_SECONDS" \
    --json > "$TMP_JSON" 2> "$TMP_ERR"
  rc=$?
  set -e

  if [ "$rc" -eq 0 ]; then
    break
  fi

  if [ "$attempt" -lt "$OPENCLAW_RETRY_MAX" ] && grep -Eiq "gateway closed|service restart|ECONNREFUSED|EPIPE|socket hang up" "$TMP_ERR"; then
    echo "openclaw_exec: transient gateway error (attempt ${attempt}/${OPENCLAW_RETRY_MAX}), retrying in ${OPENCLAW_RETRY_DELAY_SECONDS}s..." >&2
    sleep "$OPENCLAW_RETRY_DELAY_SECONDS"
    attempt=$((attempt + 1))
    continue
  fi

  echo "openclaw_exec: failed after ${attempt} attempt(s), rc=${rc}" >&2
  cat "$TMP_ERR" >&2 || true
  exit "$rc"
done

# Prefer agent workspace artifact when available; many agent workflows save final deliverable there.
if [ "$OPENCLAW_PREFER_WORKSPACE_RESULT" = "1" ]; then
  WS_RESULT_PATH="/data/workspace/agents/cm/${AGENT_ID}/result.md"
  docker exec "$OPENCLAW_CONTAINER" sh -lc "test -s \"$WS_RESULT_PATH\" && cat \"$WS_RESULT_PATH\"" >"$TMP_WS_RESULT" 2>/dev/null || true
fi

python3 - "$TMP_JSON" "$OUT_FILE" "$TMP_WS_RESULT" <<'PY'
import json
import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
out = Path(sys.argv[2])
ws_path = Path(sys.argv[3])
obj = json.loads(src.read_text(encoding="utf-8"))

if obj.get("status") != "ok":
    raise SystemExit(f"openclaw agent returned non-ok status: {obj.get('status')}")

payloads = (((obj.get("result") or {}).get("payloads")) or [])
chunks = []
for p in payloads:
    text = p.get("text")
    if text:
        chunks.append(text)

if not chunks:
    raise SystemExit("openclaw agent returned no text payload")

raw = "\n\n".join(chunks).strip()
ws_raw = ws_path.read_text(encoding="utf-8").strip() if ws_path.exists() else ""

def is_contract_result(text: str) -> bool:
    if not text:
        return False
    required = [
        "# RESULT",
        "# END_RESULT",
        "## Summary",
        "## Detailed Output",
        "## Risks / Unknowns",
        "## Next Questions",
    ]
    return all(x in text for x in required)

def has_process_chatter(text: str) -> bool:
    if not text:
        return False
    lines = [ln.strip().lower() for ln in text.splitlines() if ln.strip()]
    # Only inspect early lines where action narration typically appears.
    for ln in lines[:40]:
        if re.match(r"^(let me|i see|i'll|i will|i have|task complete|task completed|now i have|checking)\b", ln):
            return True
    return False

def score(text: str) -> int:
    if not text:
        return -999
    s = 0
    if is_contract_result(text):
        s += 10
    if not has_process_chatter(text):
        s += 3
    s += min(len(text.encode("utf-8")) // 500, 6)
    return s

candidates = [
    ("workspace_result", ws_raw, score(ws_raw)),
    ("agent_payload", raw, score(raw)),
]
candidates.sort(key=lambda x: x[2], reverse=True)
chosen_name, chosen_text, chosen_score = candidates[0]

if chosen_score <= 0:
    raise SystemExit("OpenClaw output failed quality checks (missing contract or only process narration)")

if is_contract_result(chosen_text):
    out.write_text(chosen_text + ("\n" if not chosen_text.endswith("\n") else ""), encoding="utf-8")
else:
    task_id = out.parent.name.split("_")[0]
    try:
        meta = json.loads((out.parent / "meta.json").read_text(encoding="utf-8"))
        if isinstance(meta, dict) and meta.get("id"):
            task_id = str(meta["id"])
    except Exception:
        pass

    normalized = (
        f"# RESULT\n"
        f"id: {task_id}\n\n"
        f"## Summary\n"
        f"- Generated by OpenClaw agent execution ({chosen_name})\n\n"
        f"## Detailed Output\n"
        f"{chosen_text}\n\n"
        f"## Risks / Unknowns\n"
        f"- Verify factual claims before publishing\n\n"
        f"## Next Questions\n"
        f"- Any revisions needed?\n"
        f"# END_RESULT\n"
    )
    out.write_text(normalized, encoding="utf-8")
PY
