import json
import logging

from ..interfaces.kernel import ALLOWED_NAME, PROTECTED, configured_interfaces, find_key, run

BRIDGE_NAME = "nc-vlan-br0"


def _items(value):
    """Convierte listas YANG (incluido libyang.keyed_list) en una lista normal."""
    return list(value) if value else []


def _module_data(conn, xpath):
    with conn.start_session("running") as sess:
        try:
            return sess.get_data(xpath)
        except Exception:  # El módulo puede no estar instalado durante la migración.
            return {}


def _vids(value):
    """Expande la sintaxis IEEE de VIDs y rangos separados por comas."""
    if value is None:
        return set()
    result = set()
    for part in str(value).split(","):
        first, separator, last = part.partition("-")
        if separator:
            result.update(range(int(first), int(last) + 1))
        else:
            result.add(int(first))
    return result


def _bridge_configuration(conn):
    data = _module_data(conn, "/ieee802-dot1q-bridge:bridges")
    root = find_key(data, "bridges", {}) or {}
    bridges = _items(find_key(root, "bridge", []))
    if len(bridges) > 1:
        raise ValueError("El laboratorio admite exactamente un bridge IEEE 802.1Q")
    return bridges[0] if bridges else {}


def desired_vlan_ports(conn):
    """Traduce bridge-port/PVID y port-map IEEE a reglas Linux bridge vlan.

    IEEE identifica los puertos del port-map por ``port-ref`` numérico. El
    laboratorio publica una asignación estable: los bridge ports se numeran
    desde 1, ordenados lexicográficamente por nombre de interfaz.
    """
    bridge = _bridge_configuration(conn)
    if not bridge:
        return {}, {}
    components = _items(bridge.get("component", []))
    if len(components) != 1:
        raise ValueError("El bridge IEEE debe contener exactamente un componente VLAN")
    component = components[0]
    bridge_name = bridge.get("name")
    component_name = component.get("name")
    interfaces = {
        entry.get("name"): entry
        for entry in configured_interfaces(conn)
        if entry.get("name") and entry.get("enabled", True)
    }
    bridge_ports = {}
    for name, interface in interfaces.items():
        port = find_key(interface, "bridge-port", {}) or {}
        if port.get("bridge-name") == bridge_name and port.get("component-name") == component_name:
            bridge_ports[name] = port
    port_numbers = {number: name for number, name in enumerate(sorted(bridge_ports), start=1)}
    desired = {
        name: {"members": set(), "native": int(port.get("pvid", 1))}
        for name, port in bridge_ports.items()
    }
    for name, port in bridge_ports.items():
        if name in PROTECTED or not ALLOWED_NAME.fullmatch(name):
            raise ValueError(f"El bridge port {name} no es una interfaz dummy gestionada")
        if port.get("port-type") not in (None, "ieee802-dot1q-bridge:c-vlan-bridge-port"):
            raise ValueError(f"Tipo de bridge port no admitido en {name}: {port.get('port-type')}")
    registrations = find_key(component, "filtering-database", {}) or {}
    vlans = {}
    for entry in _items(registrations.get("vlan-registration-entry", [])):
        if entry.get("entry-type") != "static":
            raise ValueError("Solo se admiten vlan-registration-entry estáticas")
        vids = _vids(entry.get("vids"))
        if not vids or any(vid < 1 or vid > 4094 for vid in vids):
            raise ValueError(f"VID IEEE no admitido: {entry.get('vids')}")
        for port_map in _items(entry.get("port-map", [])):
            name = port_numbers.get(int(port_map.get("port-ref", 0)))
            details = port_map.get("static-vlan-registration-entries")
            if name is None or details is None:
                raise ValueError(f"port-ref IEEE inválido: {port_map.get('port-ref')}")
            if details.get("registrar-admin-control") == "forbidden":
                continue
            transmitted = details.get("vlan-transmitted")
            if transmitted not in ("tagged", "untagged"):
                raise ValueError(f"vlan-transmitted inválido en {name}: {transmitted}")
            for vid in vids:
                if vid in vlans and vlans[vid] != entry.get("database-id"):
                    raise ValueError(f"El VID {vid} aparece en varias filtering databases")
                vlans[vid] = entry.get("database-id")
                desired[name]["members"].add(vid)
                if transmitted == "untagged" and desired[name]["native"] != vid:
                    raise ValueError(f"El PVID de {name} debe coincidir con su VLAN sin etiqueta")
    for name, port in desired.items():
        if port["native"] not in port["members"]:
            raise ValueError(f"El PVID {port['native']} de {name} no está registrado en el port-map")
    return vlans, desired


def validate_vlan_configuration(conn):
    desired_vlan_ports(conn)


def validate_vlan_changes(changes, conn):
    """Rechaza referencias a puertos protegidos en cambios IEEE directos."""
    for change in changes:
        xpath = str(getattr(change, "xpath", ""))
        if "bridge-port" in xpath and any(f"[name='{name}']" in xpath for name in PROTECTED):
            raise ValueError("eth0 y lo no pueden ser bridge ports")


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
