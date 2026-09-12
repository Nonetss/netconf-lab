#!/usr/bin/env python3
from common import connect
with connect() as device:
    print("=== Capacidades ===")
    for capability in device.server_capabilities:
        print(capability)
    print("\n=== Configuración running ===")
    print(device.get_config(source="running").data_xml)
    print("\n=== Configuración + estado operacional ===")
    print(device.get().data_xml)
