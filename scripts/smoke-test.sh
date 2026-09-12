#!/usr/bin/env bash
# Smoke test del device NETCONF: levanta el contenedor y ejercita config,
# reconciliación de interfaces Linux y estado operacional directamente vía
# sysrepocfg, sin depender de ningún cliente NETCONF externo.
set -Eeuo pipefail

docker compose up --build -d device

printf 'Esperando al servidor NETCONF'
for _ in {1..30}; do
  if [[ "$(docker inspect --format='{{.State.Health.Status}}' netconf-device 2>/dev/null || true)" == healthy ]]; then echo; break; fi
  printf '.'; sleep 2
done
[[ "$(docker inspect --format='{{.State.Health.Status}}' netconf-device)" == healthy ]]

sysrepocfg() { docker compose exec -T device sysrepocfg "$@"; }

echo '--> running config expone al menos una interfaz'
sysrepocfg -X -d running -m ietf-interfaces -f xml | tee /tmp/netconf-running.xml >/dev/null
grep -q '<interface>' /tmp/netconf-running.xml

echo '--> edit-config crea una interfaz nueva y se refleja en el Linux dummy'
echo '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"><interface><name>smoke0</name><type xmlns:ianaift="urn:ietf:params:xml:ns:yang:iana-if-type">ianaift:ethernetCsmacd</type><enabled>true</enabled></interface></interfaces>' \
  | sysrepocfg --edit -d running -m ietf-interfaces -f xml
for _ in {1..5}; do
  if docker compose exec -T device ip link show smoke0 | grep -q ',UP,'; then break; fi
  sleep 1
done
docker compose exec -T device ip link show smoke0 | grep -q ',UP,'

echo '--> estado operacional expone oper-status de la interfaz'
sysrepocfg -X -d operational -m ietf-interfaces -f xml | tee /tmp/netconf-oper.xml >/dev/null
grep -q 'oper-status' /tmp/netconf-oper.xml

echo 'Smoke test OK'
