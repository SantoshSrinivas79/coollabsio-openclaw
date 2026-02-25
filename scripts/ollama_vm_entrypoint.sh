#!/usr/bin/env bash
set -euo pipefail

VM_ROOT="${OLLAMA_VM_ROOT:-/vm}"
STATE_DIR="${OPENCLAW_STATE_DIR:-${VM_ROOT}/.openclaw}"
WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-${VM_ROOT}/workspace}"
OLLAMA_LOG="${OLLAMA_VM_OLLAMA_LOG:-${VM_ROOT}/ollama-serve.log}"
OLLAMA_MODELS_DIR="${OLLAMA_MODELS:-${VM_ROOT}/.ollama/models}"
OPENCLAW_LOG="${OLLAMA_VM_OPENCLAW_LOG:-${VM_ROOT}/openclaw-gateway.log}"

mkdir -p "${VM_ROOT}" "${STATE_DIR}" "${WORKSPACE_DIR}" "${OLLAMA_MODELS_DIR}"

export HOME="${VM_ROOT}"
mkdir -p "${HOME}"
mkdir -p "${HOME}/.openclaw"

# Keep legacy paths consistent if tools still inspect /root/.openclaw.
if [[ ! -e /root/.openclaw ]]; then
  ln -s "${HOME}/.openclaw" /root/.openclaw 2>/dev/null || true
fi

echo "[ollama-vm] starting ollama server..."
ollama serve >"${OLLAMA_LOG}" 2>&1 &

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

echo "[ollama-vm] ollama server is ready on 11434"
echo "[ollama-vm] run inside container: ollama launch openclaw"
echo "[ollama-vm] config mode available: ollama launch openclaw --config"
echo "[ollama-vm] gateway bind env: OPENCLAW_GATEWAY_BIND=${OPENCLAW_GATEWAY_BIND:-lan}"
echo "[ollama-vm] gateway port env: OPENCLAW_GATEWAY_PORT=${OPENCLAW_GATEWAY_PORT:-18789}"

MODEL_ID="${OLLAMA_VM_OPENCLAW_MODEL:-gemma3:4b}"
if [[ "${OLLAMA_VM_AUTO_PULL_MODEL:-1}" == "1" ]]; then
  if ! ollama list | awk 'NR>1 {print $1}' | grep -Fxq "${MODEL_ID}"; then
    echo "[ollama-vm] model '${MODEL_ID}' not found locally, pulling..."
    ollama pull "${MODEL_ID}"
  else
    echo "[ollama-vm] model '${MODEL_ID}' already available locally"
  fi
fi

# Configure OpenClaw state/config on every boot to keep it idempotent.
node /app/scripts/ollama_vm_configure_openclaw.js

# Optional QMD bootstrap. Best-effort by default.
if [[ "${OLLAMA_VM_QMD_AUTO_SETUP:-1}" == "1" ]]; then
  if command -v qmd >/dev/null 2>&1; then
    echo "[ollama-vm] running qmd update..."
    (cd "${WORKSPACE_DIR}" && qmd update) || echo "[ollama-vm] qmd update failed (continuing)"
    if [[ "${OLLAMA_VM_QMD_AUTO_EMBED:-1}" == "1" ]]; then
      if find "${WORKSPACE_DIR}" -type f \( -name "*.md" -o -name "*.txt" -o -name "*.qmd" \) -print -quit | grep -q .; then
        echo "[ollama-vm] running qmd embed..."
        (cd "${WORKSPACE_DIR}" && qmd embed) || echo "[ollama-vm] qmd embed failed (continuing)"
      else
        echo "[ollama-vm] qmd embed skipped (no docs found in workspace)"
      fi
    fi
  else
    echo "[ollama-vm] qmd not installed; skipping qmd bootstrap"
  fi
fi

if [[ $# -gt 0 ]]; then
  exec "$@"
fi

if [[ "${OLLAMA_VM_START_OPENCLAW:-1}" == "1" ]]; then
  GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
  GATEWAY_BIND="${OPENCLAW_GATEWAY_BIND:-lan}"
  GATEWAY_TOKEN="${OLLAMA_VM_OPENCLAW_GATEWAY_TOKEN:-${OPENCLAW_GATEWAY_TOKEN:-ollama}}"
  echo "[ollama-vm] starting openclaw gateway on ${GATEWAY_BIND}:${GATEWAY_PORT}..."
  exec openclaw gateway \
    --port "${GATEWAY_PORT}" \
    --bind "${GATEWAY_BIND}" \
    --token "${GATEWAY_TOKEN}" \
    --allow-unconfigured \
    --verbose 2>&1 | tee -a "${OPENCLAW_LOG}"
fi

exec sleep infinity
