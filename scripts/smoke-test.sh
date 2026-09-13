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

echo '--> seed IEEE 802.1Q crea bridge filtering y puertos access/trunk'
sysrepocfg -X -d running -m ieee802-dot1q-bridge -f xml | tee /tmp/netconf-vlan-running.xml >/dev/null
grep -q '<vids>100</vids>' /tmp/netconf-vlan-running.xml
docker compose exec -T device ip -d link show dev nc-vlan-br0 | grep -q 'vlan_filtering 1'
docker compose exec -T device bridge vlan show dev dummy0 | grep -Eq '100.*PVID.*Egress Untagged'
docker compose exec -T device bridge vlan show dev dummy1 | grep -q '200'

echo '--> estado operacional IEEE expone las membresías efectivas'
sysrepocfg -X -d operational -m ieee802-dot1q-bridge -f xml | tee /tmp/netconf-vlan-oper.xml >/dev/null
grep -q '<egress-ports>dummy0</egress-ports>' /tmp/netconf-vlan-oper.xml

echo '--> el modelo IEEE rechaza un PVID reservado'
if echo '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"><interface><name>dummy0</name><bridge-port xmlns="urn:ieee:std:802.1Q:yang:ieee802-dot1q-bridge"><pvid>4095</pvid></bridge-port></interface></interfaces>' \
  | sysrepocfg --edit -d running -m ietf-interfaces -f xml; then
  echo 'El PVID reservado fue aceptado' >&2
  exit 1
fi

echo '--> forwarding se limita a la VLAN configurada'
docker compose exec -T device sh -ec '
  cleanup() {
    ip link del vlan-smoke-a 2>/dev/null || true
    ip link del vlan-smoke-b 2>/dev/null || true
    ip link del vlan-smoke-c 2>/dev/null || true
  }
  trap cleanup EXIT
  ip link add vlan-smoke-a type veth peer name vlan-smoke-a-peer
  ip link add vlan-smoke-b type veth peer name vlan-smoke-b-peer
  ip link add vlan-smoke-c type veth peer name vlan-smoke-c-peer
  for port in vlan-smoke-a vlan-smoke-b vlan-smoke-c; do
    ip link set "$port" master nc-vlan-br0
    bridge vlan del dev "$port" vid 1
    ip link set "$port" up
  done
  bridge vlan add dev vlan-smoke-a vid 300 pvid untagged
  bridge vlan add dev vlan-smoke-b vid 300 pvid untagged
  bridge vlan add dev vlan-smoke-c vid 301 pvid untagged
  ip addr add 192.0.2.1/24 dev vlan-smoke-a-peer
  ip addr add 192.0.2.2/24 dev vlan-smoke-b-peer
  ip addr add 192.0.2.3/24 dev vlan-smoke-c-peer
  ip link set vlan-smoke-a-peer up
  ip link set vlan-smoke-b-peer up
  ip link set vlan-smoke-c-peer up
  ping -c 1 -W 1 -I vlan-smoke-a-peer 192.0.2.2
  ! ping -c 1 -W 1 -I vlan-smoke-a-peer 192.0.2.3
'

echo 'Smoke test OK'
