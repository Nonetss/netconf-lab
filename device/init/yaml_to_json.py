#!/usr/bin/env python3
"""Convierte un fichero de config semilla de YAML a JSON.

Traduccion 1:1, sin logica especifica del modelo YANG: las claves
"modulo:nodo" y demas convenciones de libyang se escriben ya asi en el
YAML de entrada. Solo existe porque sysrepocfg no acepta YAML.
"""

import json
import sys

import yaml

with open(sys.argv[1], encoding="utf-8") as src:
    data = yaml.safe_load(src)

with open(sys.argv[2], "w", encoding="utf-8") as dst:
    json.dump(data, dst)
