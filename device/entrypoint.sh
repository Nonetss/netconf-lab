#!/usr/bin/env bash
set -Eeuo pipefail
export USER=root
export NP2_MODULE_DIR=/usr/share/yang/modules/netopeer2
export LN2_MODULE_DIR=/usr/share/yang/modules/libnetconf2
export NP2_MODULE_PERMS=666
export NP2_MODULE_OWNER=root
export NP2_MODULE_GROUP=root
export SYSREPOCTL_EXECUTABLE=/usr/bin/sysrepoctl
export SYSREPOCFG_EXECUTABLE=/usr/bin/sysrepocfg

printf 'root:netconf
' | chpasswd
mkdir -p /root/.ssh
chmod 700 /root/.ssh
/usr/share/netopeer2/scripts/setup.sh
# ietf-interfaces importa iana-if-type, pero necesitamos que quede
# implementado para usar identidades como ethernetCsmacd.
if ! sysrepoctl -l | awk -F'|' '
  $1 ~ /^[[:space:]]*iana-if-type[[:space:]]*$/ &&
  $3 ~ /I/ { found=1 }
  END { exit !found }
'; then
  sysrepoctl \
    -i /src/sysrepo/modules/subscribed_notifications/iana-if-type@2014-05-08.yang \
    -p 666 \
    -o root \
    -g root \
    -v2
fi
for feature in arbitrary-names pre-provisioning if-mib; do
  if ! sysrepoctl -l | awk -F'|' '$1 ~ /^ietf-interfaces / {print $NF}' | grep -qw "$feature"; then
    sysrepoctl -c ietf-interfaces -e "$feature" -v2
  fi
done
if ! sysrepoctl -l | grep -q '^sandbox-device[[:space:]]'; then
  sysrepoctl -i /opt/sandbox/yang/sandbox-device.yang -p 666 -o root -g root -v2
fi
/usr/share/netopeer2/scripts/merge_hostkey.sh
/usr/share/netopeer2/scripts/merge_config.sh
if [[ ! -f /etc/sysrepo/.sandbox-initialized ]]; then
  sysrepocfg --edit=/opt/sandbox/init/interfaces.xml -d running -f xml -m ietf-interfaces -v2
  sysrepocfg --copy-from=running -d startup -m ietf-interfaces -v2
  sysrepocfg --edit=/opt/sandbox/init/system.xml -d running -f xml -m sandbox-device -v2
  sysrepocfg --copy-from=running -d startup -m sandbox-device -v2
  touch /etc/sysrepo/.sandbox-initialized
fi
cleanup() {
  kill -TERM "${plugin_pid:-}" "${server_pid:-}" 2>/dev/null || true
  wait || true
}
trap cleanup TERM INT EXIT
python3 /opt/sandbox/app/device_plugin.py &
plugin_pid=$!
netopeer2-server -d -v2 &
server_pid=$!
wait -n "$plugin_pid" "$server_pid"
status=$?
echo "Un proceso principal terminó con estado $status" >&2
exit "$status"
