# netconf-lab

Sandbox NETCONF/YANG: **Netopeer2** (servidor NETCONF) + **Sysrepo** (datastore YANG) en un contenedor Docker (`device`). Solo usa modelos YANG **estándar** (RFC de IETF/IANA, OpenConfig) — nada de módulos propios inventados a mano. Ver `README.md` para el uso desde fuera (arranque, clientes, comandos `sysrepocfg`).

## Arrancar y probar

```bash
cp .env.example .env
docker compose up --build -d
./scripts/smoke-test.sh   # levanta el lab y verifica interfaces y VLANs
```

`docker compose down -v --remove-orphans` para reset completo (borra `sysrepo-data` y el host key).

## Arquitectura

- `device/entrypoint.py`: arranca netopeer2-server, instala módulos YANG e inicializa la config, **de forma genérica** (nada de nombres de módulo hardcodeados salvo `iana-if-type`, que necesita venir de un path fijo del propio paquete sysrepo):
  - `install_modules()` → `install_feature_modules()`: recorre `device/yang/<feature>/*.yang`; por cada módulo que `sysrepoctl -l` no conozca todavía, lo instala con `sysrepoctl -i <fichero> -s <carpeta-feature> -e '*' ...` (todas las features activadas). Si el módulo ya existe (netopeer2/sysrepo trae varios de fábrica, a veces en otra revisión), lo salta.
  - `seed_datastores()` (**en cada arranque**, no solo el primero): recorre `device/init/<feature>/*.yaml` (nunca `*.example.yaml`), convierte cada uno a JSON y lo aplica con `sysrepocfg --edit` **sin `-m`** (el JSON ya lleva sus claves cualificadas por módulo, así que un fichero puede tocar varios módulos a la vez, p.ej. `sistema.yaml` trae `ietf-system` + `ietf-netconf-acm`). Reaplicar siempre es deliberado: `sysrepo-data` sobrevive a un `--build` (solo `down -v` lo borra), y un flag de "ya inicializado" habría hecho que editar un `.yaml` y reconstruir la imagen nunca se notara — justo el bug que este lab tuvo. Un cambio hecho a mano por NETCONF en caliente se pierde en el siguiente arranque, a propósito: los ficheros en `device/init/` son la fuente de verdad.
- `device/netconf_lab/`: plugin Python (proceso separado, corre junto a `netopeer2-server`) que se conecta a Sysrepo y sirve callbacks — **esto sí es manual, no genérico**:
  - `subscriptions.py` cablea las suscripciones de cambio y los callbacks de datos operacionales para `ietf-interfaces`, `ietf-system`, `openconfig-platform` y VLAN OpenConfig; no hay callbacks RPC registrados actualmente.
  - `interfaces/kernel.py` reconcilia la config `ietf-interfaces`/`ietf-ip` contra interfaces Linux `dummy` reales del contenedor (`ip link`/`ip address`).
  - `interfaces/oper.py` sirve el estado operacional (`oper-status`, MAC, contadores...) leyendo `ip -j -s link`.
  - `vlan/kernel.py` reconcilia VLAN OpenConfig con el bridge privado `netconf-vlan-br0` y `vlan_filtering=1`; solo une interfaces dummy gestionadas y nunca `eth0`/`lo`.
  - `vlan/oper.py` expone las VLANs y membresías efectivas desde `bridge -j vlan show`.
  - `system/oper.py` sirve `ietf-system:system-state` desde el sistema del contenedor y completa el estado de los componentes configurados de `openconfig-platform` con metadatos virtuales.
- `device/init/<feature>/<módulo>.yaml`: seed de config real, convertido a JSON (`yaml_to_json.py`).
- `device/yang/<feature>/`: los `.yang` fuente, agrupados por feature (ver convención abajo).

Instalación + seed de config es genérica y cubre **todo** lo que haya en `device/yang/`/`device/init/` (incluido OpenConfig VLAN). Lo que sigue siendo manual, módulo por módulo, son los callbacks de `device/netconf_lab/`: `ietf-interfaces` reconcilia enlaces `dummy` y sirve su estado; VLAN OpenConfig los conecta a un bridge filtrado; `ietf-system` publica plataforma y relojes del contenedor; y `openconfig-platform` completa los componentes sembrados con estado virtual. No hay callbacks RPC.

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

Flujo completo después de generar: copiar `<módulo>.example.yaml` a `<módulo>.yaml` la primera vez, rellenarlo (con autocompletado, ver abajo), y `docker compose down -v && docker compose up --build -d`. La instalación del módulo y la siembra del seed son automáticas (ver "Arquitectura" arriba) — no hay que tocar `entrypoint.py`. Solo hace falta código en `device/netconf_lab/` si quieres RPCs o estado operacional (`config false`) de verdad, no solo la config sembrada.

**Cuidado con los tipos numéricos vía typedef** (`inet:port-number`, `oc-types:percentage`...): en el YAML van sin comillas (`port: 123`, no `port: "123"`). El generador ya sigue la cadena de `typedef` hasta el tipo builtin (`resolve_type_chain()` en `scripts/generate_config.py`) para que el JSON Schema los marque como `integer`, pero si el editor o alguien los cita a mano, `sysrepocfg --edit` falla al arrancar el contenedor con un error de "invalid ... value" en vez de fallar silenciosamente.

## Autocompletado en el editor

Cada `<módulo>.schema.json` generado es un JSON Schema real. `.vscode/settings.json` mapea `interfaces.yaml`/`interfaces.example.yaml` a su schema vía `yaml.schemas` (extensión `redhat.vscode-yaml`, recomendada en `.vscode/extensions.json`); los `.example.yaml` generados llevan además la cabecera `# yaml-language-server: $schema=./<módulo>.schema.json`, que activa el mismo autocompletado aunque se abra el archivo suelto sin el workspace.

## Convenciones de commit / cambios

- No hay tests de Python (`ruff` es el único gate, `select = ["E","F","I","UP","B","SIM"]`, `line-length = 110`).
- CI (`.github/workflows/docker-build.yml`) hace build + `scripts/smoke-test.sh` en cada push a `main` que lo pase, y publica a GHCR.
- Si cambias algo en `device/init/`, un `docker compose up --build -d` normal ya basta — `seed_datastores()` se reaplica en cada arranque. Si cambias algo en `device/yang/` (estructura de un módulo, no solo datos), sysrepo solo actualiza un módulo ya instalado con `sysrepoctl -U` si le subes la `revision` del `.yang`; si no, hace falta `docker compose down -v && docker compose up --build -d` para que el esquema instalado se regenere desde cero.
