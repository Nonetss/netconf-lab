#!/usr/bin/env bash
# Smoke test del device NETCONF: levanta el contenedor y ejercita config,
# reconciliación de interfaces Linux y RPCs directamente vía sysrepocfg,
# sin depender de ningún cliente NETCONF externo.
set -Eeuo pipefail

docker compose up --build -d device

printf 'Esperando al servidor NETCONF'
for _ in {1..30}; do
  if [[ "$(docker inspect --format='{{.State.Health.Status}}' netconf-device 2>/dev/null || true)" == healthy ]]; then echo; break; fi
  printf '.'; sleep 2
done
[[ "$(docker inspect --format='{{.State.Health.Status}}' netconf-device)" == healthy ]]

sysrepocfg() { docker compose exec -T device sysrepocfg "$@"; }

echo '--> running config expone ge0/ge1/lo0'
sysrepocfg -X -d running -m ietf-interfaces -f xml | tee /tmp/netconf-running.xml >/dev/null
grep -q 'ge0' /tmp/netconf-running.xml
grep -q 'ge1' /tmp/netconf-running.xml

echo '--> edit-config cambia el hostname'
echo '<system xmlns="urn:sandbox:device"><hostname>smoke-router</hostname></system>' \
  | sysrepocfg --edit -d running -m sandbox-device -f xml
sysrepocfg -X -d running -m sandbox-device -f xml | grep -q 'smoke-router'

echo '--> edit-config activa ge1 y se refleja en la interfaz Linux dummy'
echo '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"><interface><name>ge1</name><enabled>true</enabled></interface></interfaces>' \
  | sysrepocfg --edit -d running -m ietf-interfaces -f xml
for _ in {1..5}; do
  if docker compose exec -T device ip link show ge1 | grep -q ',UP,'; then break; fi
  sleep 1
done
docker compose exec -T device ip link show ge1 | grep -q ',UP,'

echo '--> RPC ping responde con paquetes recibidos'
echo '<ping xmlns="urn:sandbox:device"><destination>127.0.0.1</destination><count>2</count></ping>' \
  | sysrepocfg --rpc -f xml | tee /tmp/netconf-rpc.xml >/dev/null
grep -q 'packets-received' /tmp/netconf-rpc.xml

echo '--> estado operacional expone system/state e inventory'
sysrepocfg -X -d operational -m sandbox-device -f xml | tee /tmp/netconf-oper.xml >/dev/null
grep -q 'uptime-seconds' /tmp/netconf-oper.xml
grep -q 'chassis-0' /tmp/netconf-oper.xml

echo 'Smoke test OK'
