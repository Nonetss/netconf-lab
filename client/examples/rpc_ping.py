#!/usr/bin/env python3
import sys
from ncclient.xml_ import to_ele
from common import connect
destination = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
rpc = f"""<ping xmlns="urn:sandbox:device"><destination>{destination}</destination><count>3</count></ping>"""
with connect() as device:
    print(device.dispatch(to_ele(rpc)))
