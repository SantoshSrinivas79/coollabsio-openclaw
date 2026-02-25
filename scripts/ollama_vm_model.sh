#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

usage() {
  cat <<'EOF'
Usage:
  scripts/ollama_vm_model.sh <model-id> [options]

Options:
  --provider <name>   Provider name (default: lmstudio)
  --api <name>        Provider API type (default: openai-completions)
  --base-url <url>    Provider base URL (default: http://host.docker.internal:1234)
  --no-restart        Update .env only, do not restart ollama-vm

Examples:
  scripts/ollama_vm_model.sh openai/gpt-oss-20b
  scripts/ollama_vm_model.sh allenai/olmo-3-32b-think --provider lmstudio --api openai-completions --base-url http://host.docker.internal:1234
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

MODEL_ID="$1"
shift

PROVIDER="lmstudio"
API_TYPE="openai-completions"
BASE_URL="http://host.docker.internal:1234"
RESTART=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider)
      PROVIDER="${2:-}"
      shift 2
      ;;
    --api)
      API_TYPE="${2:-}"
      shift 2
      ;;
    --base-url)
      BASE_URL="${2:-}"
      shift 2
      ;;
    --no-restart)
      RESTART=0
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "${MODEL_ID}" == -* ]]; then
  echo "First argument must be a model id, got: ${MODEL_ID}" >&2
  usage
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Create it from .env.example first." >&2
  exit 1
fi

upsert_env() {
  local key="$1"
  local value="$2"
  local tmp
  tmp="$(mktemp)"
  awk -v key="${key}" -v value="${value}" '
    BEGIN { done=0 }
    $0 ~ ("^" key "=") {
      print key "=" value
      done=1
      next
    }
    { print }
    END {
      if (!done) print key "=" value
    }
  ' "${ENV_FILE}" > "${tmp}"
  mv "${tmp}" "${ENV_FILE}"
}

upsert_env "OLLAMA_VM_MODEL" "${MODEL_ID}"
upsert_env "OLLAMA_VM_OPENCLAW_MODEL" "${MODEL_ID}"
upsert_env "OLLAMA_VM_PROVIDER" "${PROVIDER}"
upsert_env "OLLAMA_VM_MODEL_PROVIDER" "${PROVIDER}"
upsert_env "OLLAMA_VM_API" "${API_TYPE}"
upsert_env "OLLAMA_VM_MODEL_API" "${API_TYPE}"
upsert_env "OLLAMA_VM_BASE_URL" "${BASE_URL}"
upsert_env "OLLAMA_VM_OLLAMA_BASE_URL" "${BASE_URL}"

echo "Updated .env with:"
echo "  OLLAMA_VM_MODEL=${MODEL_ID}"
echo "  OLLAMA_VM_PROVIDER=${PROVIDER}"
echo "  OLLAMA_VM_API=${API_TYPE}"
echo "  OLLAMA_VM_BASE_URL=${BASE_URL}"

if [[ "${RESTART}" -eq 1 ]]; then
  (
    cd "${ROOT_DIR}"
    docker compose up -d ollama-vm >/dev/null
  )
  echo "Reloaded ollama-vm."
  expected_primary="${PROVIDER}/${MODEL_ID}"
  for _ in $(seq 1 30); do
    actual_primary="$(
      cd "${ROOT_DIR}" && docker compose exec -T ollama-vm node -e '
        const fs = require("fs");
        try {
          const c = JSON.parse(fs.readFileSync("/vm/.openclaw/openclaw.json", "utf8"));
          console.log(c?.agents?.defaults?.model?.primary || "");
        } catch {
          console.log("");
        }
      ' 2>/dev/null | tail -n1
    )"
    if [[ "${actual_primary}" == "${expected_primary}" ]]; then
      break
    fi
    sleep 1
  done
  (
    cd "${ROOT_DIR}"
    docker compose exec -T ollama-vm node -e '
      const fs = require("fs");
      const c = JSON.parse(fs.readFileSync("/vm/.openclaw/openclaw.json", "utf8"));
      const primary = c?.agents?.defaults?.model?.primary || "";
      const provider = primary.split("/")[0] || "unknown";
      const model = primary.slice(provider.length + 1) || "unknown";
      const baseUrl = c?.models?.providers?.[provider]?.baseUrl || "unknown";
      const api = c?.models?.providers?.[provider]?.api || "unknown";
      console.log("Active primary model: " + primary);
      console.log("Provider API: " + api);
      console.log("Base URL: " + baseUrl);
      console.log("Tip: send /new in Telegram to start a fresh session on the new model.");
    '
  )
else
  echo "No restart performed. Run: docker compose up -d ollama-vm"
fi
