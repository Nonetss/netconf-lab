#!/usr/bin/env python3
import sys
from common import connect
hostname = sys.argv[1] if len(sys.argv) > 1 else "router-lab-02"
config = f"""<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <system xmlns="urn:sandbox:device"><hostname>{hostname}</hostname></system>
</config>"""
with connect() as device:
    print(device.edit_config(target="running", config=config))
    print(device.get_config(source="running", filter=("subtree", '<system xmlns="urn:sandbox:device"/>')).data_xml)
