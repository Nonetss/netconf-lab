#!/usr/bin/env python3
"""Genera de una tacada el YAML de ejemplo y el JSON Schema de TODAS
las features a partir de sus carpetas de YANG. Sin argumentos:

    uv run --with pyang python3 scripts/generate_config.py

Convencion del repo: cada carpeta bajo device/yang/<feature>/ trae
TODOS los .yang que esa feature necesita (modulo principal + imports +
augments, p.ej. device/yang/interfaz/ = ietf-interfaces + ietf-ip +
iana-if-type + ietf-yang-types + ietf-inet-types). El script recorre
TODAS las subcarpetas de device/yang/ automaticamente; para cada una
carga sus .yang en un unico contexto pyang -- asi los augments de
otros modulos (ietf-ip sobre interface) y los identityref con base en
otro modulo (iana-if-type) se resuelven -- y por cada modulo
"principal" que encuentra (uno con nodos config=true propios en la
raiz, p.ej. ietf-interfaces) escribe en device/init/<feature>/:

  <name>.example.yaml   esqueleto con un placeholder por nodo (o el
                         "default" del YANG si lo tiene). <name> sale
                         del nombre del modulo principal sin el
                         prefijo ietf-/iana- (ietf-interfaces ->
                         interfaces).
  <name>.schema.json    JSON Schema del mismo arbol -- enlazado desde
                         el .example.yaml con la cabecera
                         "# yaml-language-server: $schema=./<name>.schema.json"
                         para que la extension redhat.vscode-yaml
                         autocomplete claves y valores (incluye los
                         enum de las identities derivadas, p.ej. los
                         300 valores validos de "type").

Solo se sobreescriben esos dos ficheros generados. <name>.yaml (el
real, editado a mano) NUNCA se toca -- por eso se puede correr sin
miedo cada vez que cambies algo en device/yang/.

Requiere pyang.
"""

import json
import re
import sys
from pathlib import Path

from pyang import context, repository

INDENT = "  "
IDENTITY_RE = re.compile(r"identity\s+([\w.-]+)\s*\{(.*?)\n  \}", re.S)
BASE_RE = re.compile(r"base\s+([\w.:-]+)\s*;")
MODULE_RE = re.compile(r"^module\s+([\w.-]+)\s*\{", re.M)


def strip_prefix(name):
    return name.split(":", 1)[1] if ":" in name else name


def collect_identities(yang_dir):
    """{bare_identity_name: {"module": declaring_module, "bases": [bare_base_names]}}"""
    identities = {}
    for path in Path(yang_dir).glob("*.yang"):
        text = path.read_text(encoding="utf-8")
        mod_match = MODULE_RE.search(text)
        module_name = mod_match.group(1) if mod_match else path.stem
        for m in IDENTITY_RE.finditer(text):
            name, body = m.group(1), m.group(2)
            bases = [strip_prefix(b) for b in BASE_RE.findall(body)]
            identities[name] = {"module": module_name, "bases": bases}
    return identities


def derived_from(identities, base_name):
    """Nombres (bare) de todas las identities cuya cadena de 'base' llega a base_name."""
    result = set()
    changed = True
    while changed:
        changed = False
        for name, info in identities.items():
            if name in result:
                continue
            if base_name in info["bases"] or info["bases"] and set(info["bases"]) & result:
                result.add(name)
                changed = True
    return result


def describe_leaf(node):
    type_stmt = node.search_one("type")
    type_name = type_stmt.arg if type_stmt else "?"
    bits = [type_name]

    if type_name == "identityref":
        base = type_stmt.search_one("base")
        if base:
            bits[0] = f"identityref base {base.arg}"

    mandatory = node.search_one("mandatory")
    if mandatory and mandatory.arg == "true":
        bits.append("mandatory")

    if_features = node.search("if-feature")
    if if_features:
        bits.append("if-feature " + ",".join(f.arg for f in if_features))

    enums = type_stmt.search("enum") if type_stmt else []
    if enums:
        bits.append("enum: " + "|".join(e.arg for e in enums))

    return ", ".join(bits)


def qualified_key(node, parent_module):
    if node.i_module.arg != parent_module:
        return f"{node.i_module.arg}:{node.arg}"
    return node.arg


def yaml_key(node, parent_module):
    key = qualified_key(node, parent_module)
    return f'"{key}"' if ":" in key else key


# --- YAML skeleton -----------------------------------------------------


def emit_yaml_children(node, indent):
    """Lineas (ya indentadas 'indent' niveles) para los hijos config=true de node."""
    lines = []
    pad = INDENT * indent

    for child in getattr(node, "i_children", []):
        if not getattr(child, "i_config", True):
            continue

        if child.keyword == "choice":
            for case in getattr(child, "i_children", []):
                lines.extend(emit_yaml_children(case, indent))
            continue

        key = yaml_key(child, node.i_module.arg)

        if child.keyword == "container":
            lines.append(f"{pad}{key}:")
            lines.extend(emit_yaml_children(child, indent + 1))
        elif child.keyword == "list":
            lines.append(f"{pad}{key}:")
            item_lines = emit_yaml_children(child, indent + 1)
            if not item_lines:
                lines.append(f"{pad}  - {{}}")
                continue
            first = item_lines[0][len(INDENT * (indent + 1)) :]
            lines.append(f"{pad}- {first}")
            lines.extend(item_lines[1:])
        elif child.keyword == "leaf-list":
            lines.append(f"{pad}{key}: []  # leaf-list, {describe_leaf(child)}")
        elif child.keyword == "leaf":
            default = child.search_one("default")
            value = default.arg if default else "null"
            lines.append(f"{pad}{key}: {value}  # {describe_leaf(child)}")
        else:
            lines.append(f"{pad}# {child.keyword} {key} (no soportado por el generador)")

    return lines


def build_yaml(ctx, schema_filename):
    out = [f"# yaml-language-server: $schema=./{schema_filename}"]
    for module in ctx.modules.values():
        for child in getattr(module, "i_children", []):
            if not getattr(child, "i_config", True):
                continue
            out.append(f'"{child.i_module.arg}:{child.arg}":')  # top-level: siempre cualificado
            out.extend(emit_yaml_children(child, 1))
    return out


# --- JSON Schema ---------------------------------------------------------


INTEGER_TYPES = ("int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64")


def resolve_type_chain(type_stmt):
    """Sigue la cadena de typedefs (i_typedef, ya resuelto por pyang tras
    ctx.validate()) hasta el tipo builtin final. inet:port-number,
    oc-types:percentage, etc. son typedefs sobre uint16/uint8 -- sin esto
    salen como "string" en el schema, lo cual invita a poner comillas en el
    YAML y eso revienta sysrepocfg (numero no puede venir como string)."""
    current = type_stmt
    while True:
        typedef = getattr(current, "i_typedef", None)
        if typedef is None:
            return current.arg, current
        current = typedef.search_one("type")


def leaf_schema(node, identities):
    type_stmt = node.search_one("type")
    if type_stmt is None:
        return {"type": "string"}
    builtin, terminal = resolve_type_chain(type_stmt)
    description_bits = []

    if builtin == "boolean":
        schema = {"type": "boolean"}
    elif builtin in INTEGER_TYPES:
        schema = {"type": "integer"}
    elif builtin == "enumeration":
        schema = {"type": "string", "enum": [e.arg for e in terminal.search("enum")]}
    elif builtin == "bits":
        # valor real es una lista de bits separados por espacio (p.ej. "create update"),
        # no un enum estricto de una sola opcion -- se documenta en la description.
        names = [b.arg for b in terminal.search("bit")]
        schema = {"type": "string"}
        if names:
            description_bits.append("bits (separados por espacio): " + "|".join(names))
    elif builtin == "identityref":
        base_stmt = terminal.search_one("base") or type_stmt.search_one("base")
        base_name = strip_prefix(base_stmt.arg) if base_stmt else None
        values = []
        if base_name:
            for bare in sorted(derived_from(identities, base_name)):
                values.append(f"{identities[bare]['module']}:{bare}")
        schema = {"type": "string"}
        if values:
            schema["enum"] = values
    else:
        schema = {"type": "string"}

    default = node.search_one("default")
    if default:
        if schema.get("type") == "boolean":
            schema["default"] = default.arg == "true"
        elif schema.get("type") == "integer":
            schema["default"] = int(default.arg)
        else:
            schema["default"] = default.arg

    mandatory = node.search_one("mandatory")
    if mandatory and mandatory.arg == "true":
        description_bits.append("mandatory")
    for f in node.search("if-feature"):
        description_bits.append(f"requires feature '{f.arg}'")
    if description_bits:
        schema["description"] = "; ".join(description_bits)

    return schema


def node_schema(node, identities):
    properties = {}
    required = []

    for child in getattr(node, "i_children", []):
        if not getattr(child, "i_config", True):
            continue

        if child.keyword == "choice":
            for case in getattr(child, "i_children", []):
                sub = node_schema(case, identities)
                properties.update(sub["properties"])
            continue

        key = qualified_key(child, node.i_module.arg)

        if child.keyword == "container":
            properties[key] = node_schema(child, identities)
        elif child.keyword == "list":
            properties[key] = {"type": "array", "items": node_schema(child, identities)}
        elif child.keyword == "leaf-list":
            properties[key] = {"type": "array", "items": leaf_schema(child, identities)}
        elif child.keyword == "leaf":
            properties[key] = leaf_schema(child, identities)
            mandatory = child.search_one("mandatory")
            if mandatory and mandatory.arg == "true":
                required.append(key)

    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def build_schema(ctx, identities):
    root_properties = {}
    root_titles = []
    for module in ctx.modules.values():
        for child in getattr(module, "i_children", []):
            if not getattr(child, "i_config", True):
                continue
            root_properties[f"{child.i_module.arg}:{child.arg}"] = node_schema(child, identities)
            root_titles.append(module.arg)

    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": f"{', '.join(dict.fromkeys(root_titles))} config seed",
        "type": "object",
        "properties": root_properties,
        "additionalProperties": False,
    }, root_properties


# --- carga y CLI -----------------------------------------------------------


def load_yang_dir(yang_dir):
    """Carga todos los .yang de la carpeta en un unico contexto pyang y lo valida."""
    # use_env=False: pyang por defecto tambien busca en sys.prefix/share/yang/modules
    # (modulos que trae el propio paquete), lo que puede colar una revision distinta
    # de un modulo que ya tenemos en la carpeta y romper el resto de augments.
    ctx = context.Context(repository.FileRepository(str(yang_dir), use_env=False))
    for yang_path in sorted(Path(yang_dir).glob("*.yang")):
        with open(yang_path, encoding="utf-8") as fh:
            ctx.add_module(str(yang_path), fh.read())
    ctx.validate()

    fatal = [e for e in ctx.errors if e[1].is_error]
    if fatal:
        for e in ctx.errors:
            print(f"pyang: {e}", file=sys.stderr)
        sys.exit(1)
    return ctx


REPO_ROOT = Path(__file__).resolve().parent.parent
YANG_ROOT = REPO_ROOT / "device" / "yang"
INIT_ROOT = REPO_ROOT / "device" / "init"

_STRIPPED_PREFIXES = ("ietf-", "iana-")


def module_base_name(module_name):
    for prefix in _STRIPPED_PREFIXES:
        if module_name.startswith(prefix):
            return module_name[len(prefix) :]
    return module_name


def primary_module_names(ctx):
    """Modulos con nodos config=true propios en la raiz, en orden de aparicion."""
    names = []
    for module in ctx.modules.values():
        if any(getattr(c, "i_config", True) for c in getattr(module, "i_children", [])):
            if module.arg not in names:
                names.append(module.arg)
    return names


def discover_feature_dirs():
    """Subcarpetas de device/yang/ que traen al menos un .yang (una por feature)."""
    if not YANG_ROOT.is_dir():
        return []
    return sorted(d for d in YANG_ROOT.iterdir() if d.is_dir() and any(d.glob("*.yang")))


def generate_feature(feature_dir):
    ctx = load_yang_dir(feature_dir)
    identities = collect_identities(feature_dir)

    schema, root_properties = build_schema(ctx, identities)
    if not root_properties:
        print("  (sin nodos config=true en la raiz, se ignora)", file=sys.stderr)
        return

    primaries = primary_module_names(ctx)
    base_name = module_base_name(primaries[0]) if len(primaries) == 1 else feature_dir.name

    schema_filename = f"{base_name}.schema.json"
    yaml_lines = build_yaml(ctx, schema_filename)

    out_dir = INIT_ROOT / feature_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    # Solo se sobreescriben los .example.yaml/.schema.json generados -- el
    # <base_name>.yaml real (editado a mano) nunca se toca aqui.
    (out_dir / f"{base_name}.example.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    (out_dir / schema_filename).write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"  {(out_dir / f'{base_name}.example.yaml').relative_to(REPO_ROOT)}")
    print(f"  {(out_dir / schema_filename).relative_to(REPO_ROOT)}")


def main():
    feature_dirs = discover_feature_dirs()
    if not feature_dirs:
        print(f"Ninguna carpeta con .yang bajo {YANG_ROOT}", file=sys.stderr)
        sys.exit(1)

    for feature_dir in feature_dirs:
        print(f"{feature_dir.relative_to(REPO_ROOT)}:")
        generate_feature(feature_dir)


if __name__ == "__main__":
    main()
