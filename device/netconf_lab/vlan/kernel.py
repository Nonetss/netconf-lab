import json
import logging

import sysrepo  # pyright: ignore[reportMissingImports] -- solo existe dentro de la imagen Netopeer2

from ..interfaces.kernel import ALLOWED_NAME, PROTECTED, configured_interfaces, find_key, run

BRIDGE_NAME = "netconf-vlan-br0"


def _module_data(conn, xpath):
    with conn.start_session("running") as sess:
        try:
            return sess.get_data(xpath)
        except sysrepo.SysrepoNotFoundError:
            return {}


def _config(entry):
    return find_key(entry, "config", {}) or {}


def _vlan_ids(value):
    """Expande el formato OpenConfig de VLAN individual o intervalo."""
    if value is None:
        return set()
    values = value if isinstance(value, list) else [value]
    result = set()
    for item in values:
        text = str(item)
        if ".." in text:
            first, last = text.split("..", 1)
            result.update(range(int(first), int(last) + 1))
        else:
            result.add(int(item))
    return result


def configured_vlans(conn):
    data = _module_data(conn, "/openconfig-network-instance:network-instances")
    root = find_key(data, "network-instances", {})
    instances = find_key(root, "network-instance", []) or []
    vlans = {}
    for instance in instances:
        instance_name = instance.get("name") or _config(instance).get("name", "")
        vlan_root = find_key(instance, "vlans", {}) or {}
        for vlan in find_key(vlan_root, "vlan", []) or []:
            config = _config(vlan)
            vlan_id = config.get("vlan-id", vlan.get("vlan-id"))
            if vlan_id is None:
                continue
            vlan_id = int(vlan_id)
            if vlan_id in vlans:
                raise ValueError(f"La VLAN {vlan_id} está definida en más de una network-instance")
            vlans[vlan_id] = {
                "id": vlan_id,
                "name": config.get("name", ""),
                "active": config.get("status", "ACTIVE") == "ACTIVE",
                "network_instance": instance_name,
            }
    return vlans


def configured_ports(conn):
    data = _module_data(conn, "/openconfig-interfaces:interfaces")
    root = find_key(data, "interfaces", {})
    interfaces = find_key(root, "interface", []) or []
    ports = {}
    for interface in interfaces:
        name = interface.get("name") or _config(interface).get("name", "")
        ethernet = find_key(interface, "ethernet", {}) or {}
        switched = find_key(ethernet, "switched-vlan", {}) or {}
        config = _config(switched)
        mode = config.get("interface-mode")
        if mode:
            ports[name] = {
                "mode": str(mode).split(":")[-1],
                "access_vlan": config.get("access-vlan"),
                "native_vlan": config.get("native-vlan"),
                "trunk_vlans": _vlan_ids(config.get("trunk-vlans", [])),
            }
    return ports


def desired_vlan_ports(conn):
    managed = {
        entry.get("name"): entry
        for entry in configured_interfaces(conn)
        if entry.get("name") and entry.get("enabled", True)
    }
    vlans = configured_vlans(conn)
    ports = configured_ports(conn)
    desired = {}
    for name, port in ports.items():
        if name in PROTECTED:
            raise ValueError(f"La interfaz protegida {name} no puede ser un puerto VLAN")
        if name not in managed:
            raise ValueError(f"El puerto VLAN {name} no es una interfaz dummy gestionada")
        if not ALLOWED_NAME.fullmatch(name):
            raise ValueError(f"Nombre de puerto VLAN no permitido: {name}")
        mode = port["mode"]
        if mode == "ACCESS":
            if port["access_vlan"] is None or port["native_vlan"] is not None or port["trunk_vlans"]:
                raise ValueError(f"El puerto access {name} debe tener únicamente access-vlan")
            members = {int(port["access_vlan"])}
            native = int(port["access_vlan"])
        elif mode == "TRUNK":
            if port["access_vlan"] is not None:
                raise ValueError(f"El trunk {name} no puede definir access-vlan")
            native = int(port["native_vlan"]) if port["native_vlan"] is not None else None
            members = set(port["trunk_vlans"]) or set(vlans)
            if native is not None:
                members.add(native)
        else:
            raise ValueError(f"Modo VLAN no admitido en {name}: {mode}")
        unavailable = sorted(vlan for vlan in members if vlan not in vlans or not vlans[vlan]["active"])
        if unavailable:
            raise ValueError(f"El puerto {name} referencia VLANs inexistentes o suspendidas: {unavailable}")
        desired[name] = {"members": members, "native": native}
    return vlans, desired


def validate_vlan_configuration(conn):
    desired_vlan_ports(conn)


def validate_vlan_changes(changes, conn):
    """Rechaza referencias nuevas a VLAN inexistente antes del commit.

    sysrepo-python no expone la sesión candidata al callback; por ello las
    referencias modificadas se contrastan contra las VLAN ya confirmadas y la
    validación integral se repite tras el commit durante la reconciliación.
    """
    vlans = configured_vlans(conn)
    for change in changes:
        xpath = str(getattr(change, "xpath", ""))
        if not any(leaf in xpath for leaf in ("access-vlan", "native-vlan", "trunk-vlans")):
            continue
        value = getattr(change, "value", None)
        if value is None:
            continue
        missing = _vlan_ids(value) - set(vlans)
        if missing:
            raise sysrepo.SysrepoValidationFailedError(
                f"Referencia a VLAN inexistente: {sorted(missing)}"
            )


def _bridge_ports():
    result = run("ip", "-j", "link", "show", "master", BRIDGE_NAME, check=False)
    if result.returncode:
        return []
    return [entry["ifname"] for entry in json.loads(result.stdout)]


def _bridge_exists():
    return run("ip", "link", "show", "dev", BRIDGE_NAME, check=False).returncode == 0


def reconcile_vlans(conn):
    _, ports = desired_vlan_ports(conn)
    current_ports = _bridge_ports() if _bridge_exists() else []
    for name in current_ports:
        if name not in PROTECTED:
            run("ip", "link", "set", "dev", name, "nomaster")
    if _bridge_exists():
        run("ip", "link", "delete", "dev", BRIDGE_NAME, "type", "bridge")
    if not ports:
        return
    run("ip", "link", "add", "name", BRIDGE_NAME, "type", "bridge", "vlan_filtering", "1")
    run("ip", "link", "set", "dev", BRIDGE_NAME, "up")
    for name, port in ports.items():
        if run("ip", "link", "show", "dev", name, check=False).returncode:
            logging.warning("Puerto VLAN %s ausente; se publicará como no operativo", name)
            continue
        run("ip", "link", "set", "dev", name, "master", BRIDGE_NAME)
        # El bridge añade VLAN 1 por defecto al convertirse en esclavo; dejarla
        # activa abriría forwarding no configurado entre puertos.
        run("bridge", "vlan", "del", "dev", name, "vid", "1")
        for vlan in sorted(port["members"]):
            args = ["bridge", "vlan", "add", "dev", name, "vid", str(vlan)]
            if vlan == port["native"]:
                args.extend(("pvid", "untagged"))
            run(*args)
