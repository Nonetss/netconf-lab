#!/usr/bin/env bash
set -Eeuo pipefail
docker compose up --build -d
printf 'Esperando al servidor NETCONF'
for _ in {1..30}; do
  if [[ "$(docker inspect --format='{{.State.Health.Status}}' netconf-device 2>/dev/null || true)" == healthy ]]; then echo; break; fi
  printf '.'; sleep 2
done
[[ "$(docker inspect --format='{{.State.Health.Status}}' netconf-device)" == healthy ]]
docker compose exec -T client python examples/get_all.py >/tmp/netconf-get.xml
grep -q 'router-lab-01' /tmp/netconf-get.xml
grep -q 'ge0' /tmp/netconf-get.xml
docker compose exec -T client python examples/edit_hostname.py smoke-router >/tmp/netconf-edit.xml
grep -q 'smoke-router' /tmp/netconf-edit.xml
docker compose exec -T client python examples/toggle_interface.py ge1 true >/tmp/netconf-interface.xml
grep -q 'ge1' /tmp/netconf-interface.xml
docker compose exec -T client python examples/rpc_ping.py 127.0.0.1 >/tmp/netconf-rpc.xml
grep -q 'packets-received' /tmp/netconf-rpc.xml
echo 'Smoke test OK'
