import json

from ..interfaces.kernel import run
from .kernel import _bridge_configuration, _items, desired_vlan_ports


def bridge_vlan_snapshot():
    result = run("bridge", "-j", "vlan", "show", check=False)
    if result.returncode:
        return {}
    memberships = {}
    for interface in json.loads(result.stdout):
        name = interface.get("ifname")
        for vlan in interface.get("vlans", []):
            vlan_id = vlan.get("vlan")
            if name and vlan_id is not None:
                memberships.setdefault(int(vlan_id), set()).add(name)
    return memberships


async def vlan_oper_data(xpath, private_data):
    conn = private_data
    vlans, desired_ports = desired_vlan_ports(conn)
    effective = bridge_vlan_snapshot()
    bridge = _bridge_configuration(conn)
    if not bridge:
        return {}
    components = _items(bridge.get("component"))
    component = components[0] if components else {}
    component_name = component.get("name")
    component_state = {
        "name": component_name,
        "ports": len(desired_ports),
        "bridge-vlan": {
            "max-vids": 4094,
            "vlan": [
                {
                    "vid": vid,
                    "egress-ports": sorted(effective.get(vid, set())),
                    "untagged-ports": sorted(
                        name
                        for name, port in desired_ports.items()
                        if port["native"] == vid and name in effective.get(vid, set())
                    ),
                }
                for vid in sorted(vlans)
            ],
        },
    }
    return {
        "bridges": {
            "bridge": [
                {
                    "name": bridge["name"],
                    "ports": len(desired_ports),
                    "components": 1,
                    "component": [component_state],
                }
            ]
        }
    }
