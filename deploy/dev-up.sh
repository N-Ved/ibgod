#!/bin/bash
# Start an ISOLATED test copy of IB God on 127.0.0.1:18081 with a fixed fake user (no Caddy, no Authelia, own network).
#   deploy/dev-up.sh [username] [filebrowser-data-dir]     start        deploy/dev-up.sh down     stop
# The FileBrowser folder defaults to the real one (read-only); tests pass a scratch copy to try access rules safely.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "down" ]; then docker rm -f ibgod-dev >/dev/null 2>&1 || true; docker network rm ibgod_dev >/dev/null 2>&1 || true; echo stopped; exit 0; fi
USERNAME="${1:-devtest}"
FB="${2:-/opt/fileserver/filebrowser-data}"
docker build -q -t local/ibgod:dev . >/dev/null
docker network inspect ibgod_dev >/dev/null 2>&1 || docker network create ibgod_dev >/dev/null
docker rm -f ibgod-dev >/dev/null 2>&1 || true
docker run -d --name ibgod-dev --network ibgod_dev --user 1000:1000 --read-only --tmpfs /tmp:size=256m --cap-drop ALL --security-opt no-new-privileges --memory 3g --cpus 3 \
  -e TZ=Europe/Stockholm -e IBGOD_DEV_USER="$USERNAME" -e IBGOD_AUTO_INDEX=0 -e IBGOD_BACKGROUND_JOBS=0 -e IBGOD_PUBLIC_HOSTS=127.0.0.1:18081,ibgod-dev:8080 \
  -p 127.0.0.1:18081:8080 -v /mnt/files/docs:/library:ro -v "$PWD/data:/data" -v "$FB:/filebrowser:ro" local/ibgod:dev >/dev/null
for i in $(seq 1 40); do curl -fsS -m 2 http://127.0.0.1:18081/healthz >/dev/null 2>&1 && break; sleep 1; done
curl -fsS -m 3 http://127.0.0.1:18081/healthz && echo " app up as user '$USERNAME' at http://127.0.0.1:18081 (FileBrowser data: $FB)"
