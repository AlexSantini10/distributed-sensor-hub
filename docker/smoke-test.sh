#!/usr/bin/env bash
set -euo pipefail

image="${1:-distributed-sensor-hub:ci-smoke}"
container_name="distributed-sensor-hub-smoke-${GITHUB_RUN_ID:-local}-$$"

cleanup() {
  docker rm -f "${container_name}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run --rm -d \
  --name "${container_name}" \
  -p 127.0.0.1::10000 \
  -e NODE_ID=smoke-node \
  -e HOST=0.0.0.0 \
  -e PORT=9000 \
  -e WEB_API_PORT=10000 \
  -e BOOTSTRAP_PEERS= \
  -e LOG_LEVEL=INFO \
  -e LOG_FILE=/tmp/smoke-node.log \
  -e CLEAR_LOG=true \
  -e SENSORS=0 \
  "${image}" >/dev/null

web_port="$(docker port "${container_name}" 10000/tcp | awk -F: 'NR == 1 { print $NF }')"
deadline=$((SECONDS + 30))

until curl --fail --silent --show-error \
  "http://127.0.0.1:${web_port}/api/state" >/dev/null &&
  curl --fail --silent --show-error \
  "http://127.0.0.1:${web_port}/ui" >/dev/null; do
  if (( SECONDS >= deadline )); then
    docker logs "${container_name}"
    exit 1
  fi
  sleep 1
done

echo "Docker image smoke test passed on port ${web_port}"
