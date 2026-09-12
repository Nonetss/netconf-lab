#!/usr/bin/env python3
import sys
from common import connect
name = sys.argv[1] if len(sys.argv) > 1 else "ge1"
enabled = sys.argv[2].lower() if len(sys.argv) > 2 else "true"
if enabled not in {"true", "false"}:
    raise SystemExit("Uso: toggle_interface.py [interfaz] [true|false]")
config = f"""<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">
    <interface><name>{name}</name><enabled>{enabled}</enabled></interface>
  </interfaces>
</config>"""
with connect() as device:
    print(device.edit_config(target="running", config=config, default_operation="merge"))
    print(device.get(filter=("subtree", f'<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"><interface><name>{name}</name></interface></interfaces>')).data_xml)
