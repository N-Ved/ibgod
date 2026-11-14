#!/bin/bash
# Start an ISOLATED test copy of IB God (app + model) on its own network, reachable only at 127.0.0.1:18081.
# It does not touch Caddy, Authelia or the shared docker networks. Identity is faked with a fixed test user.
#   deploy/dev-up.sh [username]     start        deploy/dev-up.sh down     stop
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "down" ]; then docker rm -f ibgod-dev ibgod-dev-llm >/dev/null 2>&1 || true; docker network rm ibgod_dev >/dev/null 2>&1 || true; echo stopped; exit 0; fi
USERNAME="${1:-devtest}"
docker build -q -t local/ibgod:dev . >/dev/null
docker network inspect ibgod_dev >/dev/null 2>&1 || docker network create ibgod_dev >/dev/null
docker rm -f ibgod-dev ibgod-dev-llm >/dev/null 2>&1 || true
docker run -d --name ibgod-dev-llm --network ibgod_dev --network-alias llm --user 1000:1000 --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  --memory 6g --cpus 4 -v "$PWD/models:/models:ro" ghcr.io/ggml-org/llama.cpp@sha256:c7d58273d753d33a352e5c41ab300c5ae040a16fa4b202231bb606478065c124 \
  --model /models/Qwen3.5-4B-Q4_K_M.gguf --ctx-size 12288 --threads 4 --parallel 1 --reasoning-budget 0 --no-webui --host 0.0.0.0 --port 8080 >/dev/null
docker run -d --name ibgod-dev --network ibgod_dev --user 1000:1000 --read-only --tmpfs /tmp:size=256m --cap-drop ALL --security-opt no-new-privileges --memory 3g --cpus 3 \
  -e TZ=Europe/Stockholm -e IBGOD_DEV_USER="$USERNAME" -e IBGOD_LLM_URL=http://llm:8080 -e IBGOD_PUBLIC_HOSTS=127.0.0.1:18081,ibgod-dev:8080 \
  -p 127.0.0.1:18081:8080 -v /mnt/files/docs:/library:ro -v "$PWD/data:/data" local/ibgod:dev >/dev/null
for i in $(seq 1 40); do curl -fsS -m 2 http://127.0.0.1:18081/healthz >/dev/null 2>&1 && break; sleep 1; done
curl -fsS -m 3 http://127.0.0.1:18081/healthz && echo " app up as user '$USERNAME' at http://127.0.0.1:18081"
