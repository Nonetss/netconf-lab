import json

from ..interfaces.kernel import link_snapshot, run
from .kernel import desired_vlan_ports


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
    links = link_snapshot()
    effective = bridge_vlan_snapshot()
    instances = {}
    for vlan in vlans.values():
        instance = instances.setdefault(vlan["network_instance"], [])
        members = []
        for name, port in desired_ports.items():
            if vlan["id"] not in port["members"]:
                continue
            link = links.get(name)
            if name in effective.get(vlan["id"], set()) and link:
                members.append({"state": {"interface": name}})
            elif not link:
                # El modelo no tiene un estado explícito por miembro; la ausencia
                # queda visible al no publicar una membresía efectiva.
                continue
        instance.append(
            {
                "vlan-id": vlan["id"],
                "state": {
                    "vlan-id": vlan["id"],
                    "name": vlan["name"],
                    "status": "ACTIVE" if vlan["active"] else "SUSPENDED",
                },
                "members": {"member": members},
            }
        )
    return {
        "network-instances": {
            "network-instance": [
                {"name": name, "vlans": {"vlan": vlan_list}} for name, vlan_list in instances.items()
            ]
        }
    }
