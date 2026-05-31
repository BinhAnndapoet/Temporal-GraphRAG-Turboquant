#!/usr/bin/env bash
set -euo pipefail

# Canonical one-command launcher for local Turboquant runtime + Streamlit demo.
# - Starts llama-server in tmux session: llm_srv
# - Waits until /v1/models is ready
# - Starts Streamlit demo in tmux session: demo

LLAMA_REPO="${LLAMA_REPO:-/home/guest/Projects/Research/llama-cpp-turboquant}"
TGRAG_REPO="${TGRAG_REPO:-/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant}"
CONDA_ENV="${CONDA_ENV:-turboquant}"

MODEL_PATH="${MODEL_PATH:-/home/guest/Projects/Research/llama-cpp-turboquant/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf}"
MODEL_ALIAS="${MODEL_ALIAS:-qwen25-7b-q8-ctkq8-ctvturbo3-c131072-p4-np3072}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"

CTX="${CTX:-131072}"
PARALLEL="${PARALLEL:-4}"
NPREDICT="${NPREDICT:-3072}"

SERVER_SESSION="${SERVER_SESSION:-llm_srv}"
DEMO_SESSION="${DEMO_SESSION:-demo}"
DEMO_PORT="${DEMO_PORT:-8501}"

START_DEMO=1
RESTART=1
WAIT_TIMEOUT="${WAIT_TIMEOUT:-120}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Starts local llama-server + Streamlit demo stack in tmux.

Options:
  --server-only         Start llama-server only (skip demo)
  --no-restart          Do not kill existing tmux sessions before start
  --wait-timeout SEC    Wait timeout for /v1/models readiness (default: ${WAIT_TIMEOUT})
  -h, --help            Show this help

Environment overrides (optional):
  LLAMA_REPO, TGRAG_REPO, CONDA_ENV,
  MODEL_PATH, MODEL_ALIAS, HOST, PORT,
  CTX, PARALLEL, NPREDICT,
  SERVER_SESSION, DEMO_SESSION, DEMO_PORT, WAIT_TIMEOUT
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server-only)
      START_DEMO=0
      shift
      ;;
    --no-restart)
      RESTART=0
      shift
      ;;
    --wait-timeout)
      WAIT_TIMEOUT="${2:-}"
      if [[ -z "${WAIT_TIMEOUT}" ]]; then
        echo "[ERROR] --wait-timeout requires a value (seconds)." >&2
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v tmux >/dev/null 2>&1; then
  echo "[ERROR] tmux not found. Please install tmux first." >&2
  exit 1
fi

if [[ ! -x "${LLAMA_REPO}/build/bin/llama-server" ]]; then
  echo "[ERROR] llama-server binary not found: ${LLAMA_REPO}/build/bin/llama-server" >&2
  exit 1
fi

if [[ ! -f "${MODEL_PATH}" ]]; then
  echo "[ERROR] model file not found: ${MODEL_PATH}" >&2
  exit 1
fi

echo "[INFO] Launch config:"
echo "  LLAMA_REPO   = ${LLAMA_REPO}"
echo "  TGRAG_REPO   = ${TGRAG_REPO}"
echo "  MODEL_PATH   = ${MODEL_PATH}"
echo "  MODEL_ALIAS  = ${MODEL_ALIAS}"
echo "  HOST:PORT    = ${HOST}:${PORT}"
echo "  CTX/PAR/NP   = ${CTX}/${PARALLEL}/${NPREDICT}"
echo "  START_DEMO   = ${START_DEMO}"

if [[ "${RESTART}" == "1" ]]; then
  tmux kill-session -t "${SERVER_SESSION}" 2>/dev/null || true
  tmux kill-session -t "${DEMO_SESSION}" 2>/dev/null || true
fi

tmux new -s "${SERVER_SESSION}" -d
tmux send-keys -t "${SERVER_SESSION}" "conda activate ${CONDA_ENV} && cd ${LLAMA_REPO} && ./build/bin/llama-server \
  -m ${MODEL_PATH} \
  --alias ${MODEL_ALIAS} \
  --host ${HOST} --port ${PORT} \
  -ctk q8_0 -ctv turbo3 -fa on -ngl 99 \
  -c ${CTX} --parallel ${PARALLEL} --n-predict ${NPREDICT}" C-m

echo "[INFO] Waiting for server readiness: http://${HOST}:${PORT}/v1/models"
ready=0
for ((i=1; i<=WAIT_TIMEOUT; i++)); do
  if curl -fsS "http://${HOST}:${PORT}/v1/models" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done

if [[ "${ready}" != "1" ]]; then
  echo "[ERROR] Server not ready within ${WAIT_TIMEOUT}s." >&2
  echo "[HINT] Check logs with: tmux capture-pane -pt ${SERVER_SESSION} | tail -n 80" >&2
  exit 1
fi

echo "[OK] llama-server is ready."
curl -sS "http://${HOST}:${PORT}/v1/models" | head -c 500 && echo

if [[ "${START_DEMO}" == "1" ]]; then
  tmux new -s "${DEMO_SESSION}" -d
  tmux send-keys -t "${DEMO_SESSION}" "cd ${TGRAG_REPO} && conda activate ${CONDA_ENV} && streamlit run demo.py --server.port ${DEMO_PORT}" C-m
  echo "[OK] demo started: http://127.0.0.1:${DEMO_PORT}"
  echo "[INFO] In demo sidebar, use preset: Local Turboquant (recommended)."
else
  echo "[OK] server-only mode complete."
fi

echo "[INFO] Active tmux sessions:"
tmux ls | sed 's/^/  - /'
