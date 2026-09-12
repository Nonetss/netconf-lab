import datetime as dt
import os

import sysrepo  # pyright: ignore[reportMissingImports] -- solo existe dentro de la imagen Netopeer2

from ..state import boot_state

# Deriva el tipo openconfig-platform-types de un componente por su nombre.
# Solo cubre los nombres que trae el seed de este lab (chassis-0,
# routing-engine-0, fan-0, psu-0); cualquier otro cae en FRU generico.
COMPONENT_TYPES = {
    "chassis": ("openconfig-platform-types:CHASSIS", "Virtual chassis"),
    "routing-engine": ("openconfig-platform-types:CONTROLLER_CARD", "Virtual control plane"),
    "fan": ("openconfig-platform-types:FAN", "Virtual cooling"),
    "psu": ("openconfig-platform-types:POWER_SUPPLY", "Virtual power supply"),
}


def find_key(mapping, suffix, default=None):
    if not isinstance(mapping, dict):
        return default
    for key, value in mapping.items():
        if key.split(":")[-1] == suffix:
            return value
    return default


def component_type(name):
    for prefix, info in COMPONENT_TYPES.items():
        if name.startswith(prefix):
            return info
    return ("oc-platform-types:FRU", "Virtual component")


async def system_state_oper_data(xpath, private_data):
    uname = os.uname()
    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    return {
        "system-state": {
            "platform": {
                "os-name": uname.sysname,
                "os-release": uname.release,
                "os-version": uname.version,
                "machine": uname.machine,
            },
            "clock": {
                "current-datetime": now,
                "boot-datetime": boot_state.time_iso(),
            },
        }
    }


async def components_state_oper_data(xpath, private_data):
    conn = private_data
    with conn.start_session("running") as sess:
        try:
            data = sess.get_data("/openconfig-platform:components/component")
        except sysrepo.SysrepoNotFoundError:
            return {}
    root = find_key(data, "components", {})
    configured = find_key(root, "component", []) or []

    output = []
    for entry in configured:
        name = entry.get("name", "")
        type_id, description = component_type(name)
        output.append(
            {
                "name": name,
                "state": {
                    "name": name,
                    "type": type_id,
                    "description": description,
                    "mfg-name": "netconf-lab",
                    "hardware-version": "virtual-1.0",
                    "serial-no": f"LAB-{name.upper()}",
                    "part-no": f"NCLAB-{name.upper()}",
                },
            }
        )
    return {"components": {"component": output}}
