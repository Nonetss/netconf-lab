# netconf-lab

Sandbox NETCONF/YANG: **Netopeer2** (servidor NETCONF) + **Sysrepo** (datastore YANG) en un contenedor Docker (`device`). Solo usa modelos YANG **estándar** (RFC de IETF/IANA, OpenConfig) — nada de módulos propios inventados a mano. Ver `README.md` para el uso desde fuera (arranque, clientes, comandos `sysrepocfg`).

## Arrancar y probar

```bash
cp .env.example .env
docker compose up --build -d
./scripts/smoke-test.sh   # levanta el lab y verifica config/estado de interfaz
```

`docker compose down -v --remove-orphans` para reset completo (borra `sysrepo-data` y el host key).

## Arquitectura

- `device/entrypoint.py`: arranca netopeer2-server, instala módulos YANG que falten (`install_modules()`) y siembra la config inicial la primera vez (`seed_datastores()`, con un flag en `/etc/sysrepo/.sandbox-initialized`).
- `device/netconf_lab/`: plugin Python (proceso separado, corre junto a `netopeer2-server`) que se conecta a Sysrepo y sirve callbacks:
  - `subscriptions.py` cablea `subscribe_module_change` / `subscribe_oper_data_request` / `subscribe_rpc_call`.
  - `interfaces/kernel.py` reconcilia la config `ietf-interfaces`/`ietf-ip` contra interfaces Linux `dummy` reales del contenedor (`ip link`/`ip address`).
  - `interfaces/oper.py` sirve el estado operacional (`oper-status`, MAC, contadores...) leyendo `ip -j -s link`.
- `device/init/<feature>/<módulo>.yaml`: seed de config real, convertido a JSON (`yaml_to_json.py`) y cargado con `sysrepocfg` en el primer arranque.
- `device/yang/<feature>/`: los `.yang` fuente, agrupados por feature (ver convención abajo).

Hoy **solo `ietf-interfaces`/`ietf-ip` está conectado de verdad** (instalado + sembrado + con callbacks). `ietf-system` y `openconfig-platform` están en el repo como YANG + ejemplo generado, pero sin instalar ni callbacks — ver "Modelos YANG preparados pero no conectados" en `README.md`.

## Convención: una carpeta por feature en `device/yang/`

Cada `device/yang/<feature>/` trae **todos** los `.yang` que esa feature necesita: el módulo principal + todo lo que importa + todo lo que lo amplía (augments). Nada se comparte entre carpetas — cada una se carga sola en un contexto pyang aislado. Ejemplo: `device/yang/interfaz/` = `ietf-interfaces.yang` + `ietf-ip.yang` (augment con IPv4/IPv6) + `iana-if-type.yang` (identities de `type`) + `ietf-yang-types.yang` + `ietf-inet-types.yang` (tipos que los anteriores importan).

Los `.yang` no se escriben a mano: se descargan de la fuente oficial.

- IETF/IANA (`ietf-*`, `iana-*`): mirror [`YangModels/yang`](https://github.com/YangModels/yang), en `standard/ietf/RFC/` y `standard/iana/`.
- OpenConfig (`openconfig-*`): repo oficial [`openconfig/public`](https://github.com/openconfig/public), en `release/models/<área>/`.

```bash
mkdir -p device/yang/<feature> && cd device/yang/<feature>
curl -fsSL -o <modulo>.yang "https://raw.githubusercontent.com/YangModels/yang/main/standard/ietf/RFC/<modulo>%40<revision>.yang"
```

Cada `.yang` declara sus `import` al principio (`grep -n "^  import" *.yang`) — repite la descarga hasta que no falte nada.

## Generar YAML de ejemplo + JSON Schema

```bash
uv run --with pyang python3 scripts/generate_config.py
```

**Sin argumentos.** Recorre todas las subcarpetas de `device/yang/` y, por cada módulo con nodos de config en la raíz, escribe en `device/init/<feature>/`:

- `<módulo>.example.yaml` — esqueleto con placeholders (`null`, o el `default` del YANG), comentado con tipo/obligatoriedad.
- `<módulo>.schema.json` — JSON Schema del mismo árbol, con `enum` resueltos (identities derivadas incluidas — cruza módulos de la misma carpeta aunque no se importen entre sí, p.ej. `type` en `ietf-interfaces` sale de las identities de `iana-if-type`).

Solo sobreescribe esos dos ficheros generados — **nunca toca `<módulo>.yaml`** (el real, editado a mano), así que se puede correr después de cualquier cambio en `device/yang/` sin miedo a perder ediciones. `pyang` se usa vía `uv run --with pyang`, nunca como dependencia persistente del proyecto (no lo añadas a `pyproject.toml`/`uv.lock`) — asegúrate de usar `use_env=False` en `repository.FileRepository` si tocas `scripts/generate_config.py`, porque `pyang` por defecto también busca en `sys.prefix/share/yang/modules` y eso puede colar una revisión distinta de un módulo que ya tienes localmente.

Flujo completo después de generar: copiar `<módulo>.example.yaml` a `<módulo>.yaml` la primera vez, rellenarlo (con autocompletado, ver abajo), y si quieres que sirva datos reales: instalarlo en `install_modules()`, sembrarlo en `seed_datastores()` (`device/entrypoint.py`), e implementar los callbacks que haga falta en `device/netconf_lab/`.

## Autocompletado en el editor

Cada `<módulo>.schema.json` generado es un JSON Schema real. `.vscode/settings.json` mapea `interfaces.yaml`/`interfaces.example.yaml` a su schema vía `yaml.schemas` (extensión `redhat.vscode-yaml`, recomendada en `.vscode/extensions.json`); los `.example.yaml` generados llevan además la cabecera `# yaml-language-server: $schema=./<módulo>.schema.json`, que activa el mismo autocompletado aunque se abra el archivo suelto sin el workspace.

## Convenciones de commit / cambios

- No hay tests de Python (`ruff` es el único gate, `select = ["E","F","I","UP","B","SIM"]`, `line-length = 110`).
- CI (`.github/workflows/docker-build.yml`) hace build + `scripts/smoke-test.sh` en cada push a `main` que lo pase, y publica a GHCR.
- Si cambias algo en `device/yang/` o `device/init/`, reconstruye el volumen para probarlo: `docker compose down -v && docker compose up --build -d` (si no, el seed solo se recarga la primera vez, por el flag `/etc/sysrepo/.sandbox-initialized`).
