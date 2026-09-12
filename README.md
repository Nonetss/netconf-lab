# Sandbox NETCONF con Docker Compose

Laboratorio autocontenido que simula un dispositivo de red, no sólo un socket que responde. Usa **Netopeer2** como servidor NETCONF, **Sysrepo** como datastore YANG y solo modelos **estándar**: `ietf-interfaces` + `ietf-ip` (interfaces reales, reconciliadas contra el Linux del contenedor).

> `ietf-system` y `openconfig-platform` están **preparados como YANG de referencia** (`device/yang/sistema/`, `device/yang/plataforma/`) con su YAML de ejemplo y JSON Schema generados, pero **todavía no están conectados** al contenedor — no se instalan en `entrypoint.py` ni tienen callbacks en `device/netconf_lab/`. Hoy el lab solo sirve `ietf-interfaces` de verdad. Ver [Modelos YANG preparados pero no conectados](#modelos-yang-preparados-pero-no-conectados).

## Para qué sirve

Un target NETCONF real (config + estado sobre datastores de verdad) contra el que probar cosas sin tocar hardware ni un router de producción:

- Aprender o enseñar NETCONF/YANG con `netopeer2-cli` o cualquier cliente, sin depender de acceso a un dispositivo físico.
- Desarrollar y probar clientes/automatización NETCONF (scripts propios, colecciones Ansible, gateways RESTCONF, etc.) contra un servidor que reacciona de verdad — crear o activar una interfaz mueve una interfaz `dummy` real dentro del contenedor.
- Usarlo como dependencia de integración en CI para herramientas que hablan NETCONF (así se usa en `.github/workflows/docker-build.yml`, ver `scripts/smoke-test.sh`).
- Traer un modelo YANG estándar (RFC de IETF/IANA, OpenConfig) y aprender a cablear su config/estado a un backend real siguiendo la convención `device/yang/<feature>/` (ver [Añadir modelos YANG](#añadir-modelos-yang)).

## Qué simula

- NETCONF sobre SSH en TCP/830.
- Datastores `running`, `startup` y `candidate`.
- Interfaces configurables con `ietf-interfaces`/`ietf-ip` (`device/init/interfaz/interfaces.yaml` trae una interfaz `eth0` de ejemplo — el nombre y los datos son tuyos, edítalos).
- Interfaces Linux `dummy` reales dentro del namespace del contenedor; `enabled`, MTU y direcciones IPv4 se reconcilian desde la configuración YANG.
- Estado operacional de interfaz: `oper-status`, MAC, índice, velocidad y contadores de tráfico.
- Persistencia del datastore en un volumen Docker.

Sistema, inventario de chasis y RPCs de laboratorio (`ping`/`reboot`) **no están implementados ahora mismo** — existían en un modelo propio (`sandbox-device`) que se quitó del proyecto porque solo se quieren modelos estándar aquí. `ietf-system` y `openconfig-platform` son el camino previsto para recuperar esas dos primeras piezas; ver [Modelos YANG preparados pero no conectados](#modelos-yang-preparados-pero-no-conectados).

> La configuración sólo altera interfaces `dummy` del contenedor. No configura las interfaces del host ni reenvía tráfico como un router real.

## Arranque rápido

Requisitos: Docker Engine/Desktop con Compose v2. `sysrepo/netopeer2` sólo publica build `linux/amd64` (no hay `arm64` oficial ni un fork de terceros en el que confiar); `compose.yml` fija esa plataforma explícitamente, así que en un host ARM se ejecuta vía emulación QEMU en vez de nativo.

- **Docker Desktop (macOS Apple Silicon, Windows on ARM):** la emulación viene integrada, no hace falta nada más.
- **Linux arm64:** instala soporte binfmt una vez por host: `docker run --privileged --rm tonistiigi/binfmt --install all`.

Será notablemente más lento que en amd64 nativo por la emulación.

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

Credenciales de laboratorio:

- Host: `localhost`
- Puerto: `830` (cámbialo con `NETCONF_PORT` en `.env`)
- Usuario: `root`
- Contraseña: `netconf`

No expongas este servicio a Internet: las credenciales son deliberadamente simples y `hostkey_verify=False` sólo es apropiado para el laboratorio.

## Imagen publicada (sin build local)

`compose.yml` construye la imagen en tu máquina. Si solo quieres levantar el laboratorio sin compilar nada, usa `compose.prod.yml`, que apunta a la imagen ya construida en GHCR:

```bash
cp .env.example .env
docker compose -f compose.prod.yml up -d
docker compose -f compose.prod.yml ps
```

Es exactamente el mismo servicio (puerto, volumen `sysrepo-data`, red, healthcheck); la única diferencia es `image: ghcr.io/nonetss/netconf-lab:latest` + `pull_policy: always` en vez de `build:`. `.github/workflows/docker-build.yml` reconstruye y publica esa imagen en cada push a `main` que pase el smoke test, con tags `latest` y `sha-<commit>` — usa el tag por `sha` en vez de `latest` si necesitas fijar una versión concreta.

## Probar sin cliente NETCONF externo

Por ahora el laboratorio sólo levanta el contenedor `device`; no hay un cliente
NETCONF dedicado. Puedes ejercitar el datastore directamente con `sysrepocfg`
dentro del contenedor:

```bash
# Running config de interfaces
docker compose exec device sysrepocfg -X -d running -m ietf-interfaces -f xml

# Crear/activar una interfaz nueva; el cambio llega a la interfaz Linux dummy
echo '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"><interface><name>ge1</name><type xmlns:ianaift="urn:ietf:params:xml:ns:yang:iana-if-type">ianaift:ethernetCsmacd</type><enabled>true</enabled></interface></interfaces>' \
  | docker compose exec -T device sysrepocfg --edit -d running -m ietf-interfaces -f xml

# Estado operacional de interfaces
docker compose exec device sysrepocfg -X -d operational -m ietf-interfaces -f xml
```

`scripts/smoke-test.sh` automatiza estos mismos pasos.

## Cliente interactivo

```bash
docker compose exec device netopeer2-cli
```

Dentro de la CLI:

```text
connect --host 127.0.0.1 --port 830 --login root
get-config --source running
get
```

También puedes abrir la sesión NETCONF cruda (te pedirá `netconf`):

```bash
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -p 830 root@localhost -s netconf
```

## Inspección local

```bash
# Modelos YANG instalados
docker compose exec device sysrepoctl -l

# Configuración de interfaces
docker compose exec device sysrepocfg -X -d running -m ietf-interfaces

# Estado operacional completo
docker compose exec device sysrepocfg -X -d operational

# Interfaces Linux reales del contenedor
docker compose exec device ip -details address

# Logs del servidor y plugin
docker compose logs -f device
```

## Persistencia y reset

`docker compose down` conserva la configuración en `sysrepo-data`. Para volver al estado inicial y borrar el host key generado:

```bash
docker compose down -v --remove-orphans
docker compose up --build -d
```

## Añadir modelos YANG

Este proyecto solo usa modelos **estándar** (RFC de IETF/IANA, OpenConfig) — nada de módulos propios inventados a mano. El flujo completo, de "quiero este modelo" a "tengo un YAML validado con autocompletado", es este:

### 1. Convención de carpetas

Cada feature vive en su propia carpeta `device/yang/<feature>/`, con **todos** los `.yang` que necesita ahí dentro: el módulo principal + todo lo que importa (imports) + todo lo que lo amplía (augments), sin compartir nada con otras carpetas. Así cada carpeta se puede cargar sola, sin depender de qué más haya instalado. Por ejemplo `device/yang/interfaz/` trae 5 ficheros: `ietf-interfaces.yang` (el módulo que quieres) + `ietf-ip.yang` (lo amplía con IPv4/IPv6) + `iana-if-type.yang` (de donde salen los valores de `type`) + `ietf-yang-types.yang` + `ietf-inet-types.yang` (tipos que los anteriores importan).

### 2. Descarga el `.yang`

Los módulos estándar no hay que escribirlos, se descargan de la fuente. Dos sitios:

- **IETF/IANA** (`ietf-*`, `iana-*`): mirror [`YangModels/yang`](https://github.com/YangModels/yang), en `standard/ietf/RFC/` y `standard/iana/`. El nombre de fichero lleva la revisión, p.ej. `ietf-interfaces@2014-05-08.yang` (RFC 7223).
- **OpenConfig** (`openconfig-*`): repo oficial [`openconfig/public`](https://github.com/openconfig/public), en `release/models/<área>/`.

Ejemplo real, así se trajo `device/yang/interfaz/`:

```bash
mkdir -p device/yang/interfaz && cd device/yang/interfaz
BASE="https://raw.githubusercontent.com/YangModels/yang/main/standard"
curl -fsSL -o ietf-interfaces.yang "$BASE/ietf/RFC/ietf-interfaces%402014-05-08.yang"
curl -fsSL -o ietf-yang-types.yang "$BASE/ietf/RFC/ietf-yang-types%402013-07-15.yang"
curl -fsSL -o ietf-inet-types.yang "$BASE/ietf/RFC/ietf-inet-types%402013-07-15.yang"
curl -fsSL -o ietf-ip.yang        "$BASE/ietf/RFC/ietf-ip%402018-02-22.yang"
curl -fsSL -o iana-if-type.yang   "$BASE/iana/iana-if-type%402021-06-21.yang"
```

Cada `.yang` declara sus `import` al principio (`grep -n "^  import" *.yang`) — así sabes qué más te falta descargar. Repite hasta que no falte nada; `uv run --with pyang python3 -c "..."` (o directamente el paso 3) te avisa con un error de pyang si falta algún módulo.

### 3. Genera el ejemplo y el schema

```bash
uv run --with pyang python3 scripts/generate_config.py
```

Sin argumentos: recorre **todas** las subcarpetas de `device/yang/` (no hace falta decirle cuál) y por cada una que tenga nodos de configuración en la raíz escribe en `device/init/<feature>/`:

- `<módulo>.example.yaml` — esqueleto con una clave por nodo, `null` de placeholder (o el `default` del YANG si lo tiene), y un comentario con el tipo/si es obligatorio.
- `<módulo>.schema.json` — el JSON Schema de ese mismo árbol, con los `enum` ya resueltos (identities derivadas incluidas, p.ej. los ~300 valores válidos de `type` en interfaces salen de cruzar `ietf-interfaces` con las identities de `iana-if-type`).

Solo sobreescribe esos dos ficheros generados — nunca toca el `<módulo>.yaml` real editado a mano, así que se puede correr después de cada cambio en `device/yang/` sin miedo a perder nada.

### 4. Rellena el YAML real con autocompletado

Copia `<módulo>.example.yaml` a `<módulo>.yaml` la primera vez (ese es el que carga `sysrepocfg` en el primer arranque, ver `device/init/yaml_to_json.py` y `device/entrypoint.py:load_seed`) y edítalo con VS Code:

1. Instala la extensión `redhat.vscode-yaml` (ya recomendada en `.vscode/extensions.json`).
2. Abre la carpeta del repo como workspace — `.vscode/settings.json` ya mapea `interfaces.yaml`/`interfaces.example.yaml` a su `schema.json` vía `yaml.schemas`. Si en vez de eso abres el archivo suelto, la cabecera `# yaml-language-server: $schema=./<módulo>.schema.json` que llevan los `.example.yaml` generados activa el mismo autocompletado sin depender del workspace.
3. `Ctrl+Espacio` en cualquier valor te sugiere lo que el YANG permite ahí — enums, booleanos, los `enum` de identities, etc.

### 5. Conéctalo al contenedor (opcional)

Los pasos 1-4 dejan el modelo listo para editar, pero **no hacen nada dentro del lab todavía** — eso es aparte, y es justo el estado en el que están `ietf-system` y `openconfig-platform` ahora mismo (ver la sección siguiente). Para que sirva datos de verdad:

1. En `device/entrypoint.py`, añade un `sysrepoctl -i` idempotente para el módulo principal en `install_modules()` (a menos que netopeer2/sysrepo ya lo traiga instalado de fábrica — revisa `sysrepoctl -l` dentro del contenedor).
2. Si hay seed inicial, añade un `load_seed("<módulo>", "<feature>/<módulo>.yaml")` en `seed_datastores()`.
3. Implementa callbacks en `device/netconf_lab/` para los nodos `config false`, RPCs o acciones que quieras servir de verdad (mira `device/netconf_lab/interfaces/` como ejemplo de un módulo sí conectado).
4. Reconstruye y reinicia el volumen si cambió el esquema: `docker compose down -v && docker compose up --build -d`.

## Modelos YANG preparados pero no conectados

`device/yang/sistema/` (`ietf-system`, RFC 7317) y `device/yang/plataforma/` (`openconfig-platform`) ya están en el repo con sus dependencias completas, y `scripts/generate_config.py` les genera `device/init/sistema/sistema.example.yaml` y `device/init/plataforma/openconfig-platform.example.yaml` con schema para autocompletar. Pero **ninguno de los dos hace nada todavía dentro del lab**:

- `device/entrypoint.py` no los instala con `sysrepoctl -i` (el único módulo propio que instala ahora es `iana-if-type`).
- No hay ningún seed cargado para ellos en `seed_datastores()`.
- No hay callbacks en `device/netconf_lab/` sirviendo su estado operacional ni sus RPCs.

Dos detalles a tener en cuenta si los retomas:

- `sistema.example.yaml` mezcla **dos** módulos porque `ietf-system` importa `ietf-netconf-acm` (para anotar el leaf `password` como sensible) y ese módulo trae su propio árbol de configuración (`nacm:`) — el generador lo vuelca también, aunque no lo hayas pedido.
- `openconfig-platform.example.yaml` es casi todo huecos: el modelo es mayormente `config false` (el inventario de componentes lo publica el propio dispositivo), así que el "ejemplo editable" no aporta gran cosa hasta que haya un callback de datos operacionales detrás.

## Prueba automática

```bash
./scripts/smoke-test.sh
```

La prueba levanta el laboratorio y verifica lectura de la config, creación/activación de una interfaz y estado operacional.

## Base técnica

Netopeer2 implementa el servidor NETCONF sobre libyang/libnetconf2 y usa Sysrepo como datastore. El proyecto fija la imagen `sysrepo/netopeer2` por digest para evitar que una reconstrucción cambie silenciosamente; puedes sustituirla mediante `NETOPEER2_IMAGE`.
