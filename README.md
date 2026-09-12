# Sandbox NETCONF con Docker Compose

Laboratorio autocontenido que simula un dispositivo de red, no sólo un socket que responde. Usa **Netopeer2** como servidor NETCONF, **Sysrepo** como datastore YANG y solo modelos **estándar**: `ietf-interfaces` + `ietf-ip` (interfaces reales, reconciliadas contra el Linux del contenedor).

> `ietf-system` y `openconfig-platform` están **preparados como YANG de referencia** (`device/yang/sistema/`, `device/yang/plataforma/`) con su YAML de ejemplo y JSON Schema generados, pero **todavía no están conectados** al contenedor — no se instalan en `entrypoint.py` ni tienen callbacks en `device/netconf_lab/`. Hoy el lab solo sirve `ietf-interfaces` de verdad. Ver [Modelos YANG preparados pero no conectados](#modelos-yang-preparados-pero-no-conectados).

## Para qué sirve

Un target NETCONF real (config + estado + RPCs sobre datastores de verdad) contra el que probar cosas sin tocar hardware ni un router de producción:

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

> Los comandos de `sandbox-device` (`system`, `ping`, estado operacional) dependen de que `device/init/system.yaml` exista al primer arranque — `device/entrypoint.py:seed_datastores` lo carga sin comprobar que esté ahí. Si no existe, el contenedor falla al arrancar sobre un volumen limpio. Revisa que el archivo esté presente antes de un `docker compose down -v` + `up`.

```bash
# Running config de interfaces
docker compose exec device sysrepocfg -X -d running -m ietf-interfaces -f xml

# Cambiar hostname
echo '<system xmlns="urn:sandbox:device"><hostname>router-zrh-01</hostname></system>' \
  | docker compose exec -T device sysrepocfg --edit -d running -m sandbox-device -f xml

# Activar ge1; el cambio llega a la interfaz Linux dummy
echo '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"><interface><name>ge1</name><enabled>true</enabled></interface></interfaces>' \
  | docker compose exec -T device sysrepocfg --edit -d running -m ietf-interfaces -f xml

# Ejecutar el RPC YANG ping
echo '<ping xmlns="urn:sandbox:device"><destination>127.0.0.1</destination><count>3</count></ping>' \
  | docker compose exec -T device sysrepocfg --rpc -f xml

# Estado operacional completo
docker compose exec device sysrepocfg -X -d operational -m sandbox-device -f xml
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

## RPC manual

Desde `netopeer2-cli`, invoca `user-rpc` y pega:

```xml
<ping xmlns="urn:sandbox:device">
  <destination>127.0.0.1</destination>
  <count>3</count>
</ping>
```

Para simular un reinicio lógico y reiniciar el uptime:

```xml
<reboot xmlns="urn:sandbox:device">
  <delay-seconds>0</delay-seconds>
</reboot>
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

Convención: cada feature vive en su propia carpeta `device/yang/<feature>/`, con **todos** los `.yang` que necesita (módulo principal + imports + augments — p.ej. `device/yang/interfaz/` trae `ietf-interfaces` + `ietf-ip` + `iana-if-type` + `ietf-yang-types` + `ietf-inet-types`).

1. Crea `device/yang/<feature>/` y mete ahí los `.yang` (los tuyos y sus dependencias).
2. Genera el YAML de ejemplo y el JSON Schema para esa carpeta:

   ```bash
   uv run --with pyang python3 scripts/generate_config.py
   ```

   Sin argumentos: recorre todas las subcarpetas de `device/yang/` y escribe en `device/init/<feature>/` un `<módulo>.example.yaml` (esqueleto con placeholders, valores por defecto del YANG cuando los hay) y `<módulo>.schema.json` (para autocompletado, ver más abajo). Solo sobreescribe esos dos ficheros generados — nunca toca el `<módulo>.yaml` real editado a mano, así que se puede correr cuantas veces haga falta.
3. Copia `<módulo>.example.yaml` a `<módulo>.yaml` (si no existe aún) y rellena los valores reales; ese es el que carga `sysrepocfg` en el primer arranque (ver `device/init/yaml_to_json.py` y `device/entrypoint.py:load_seed`).
4. Añade en `device/entrypoint.py` un `sysrepoctl -i` idempotente para el módulo principal si el datastore no lo trae ya instalado (netopeer2/sysrepo instalan varios módulos IETF estándar de fábrica; revisa `sysrepoctl -l` dentro del contenedor).
5. Implementa callbacks en `device/netconf_lab/` para nodos `config false`, RPCs o acciones.
6. Reconstruye y reinicia el volumen si cambió el esquema: `docker compose down -v && docker compose up --build -d`.

### Autocompletado en el editor

Cada `device/init/<feature>/<módulo>.schema.json` es un JSON Schema real (tipos, `enum` de identities derivadas —p.ej. los ~300 valores válidos de `type` en interfaces—, `required`, `default`). Con la extensión `redhat.vscode-yaml` (recomendada en `.vscode/extensions.json`) y el mapeo en `.vscode/settings.json` (`yaml.schemas`), VS Code sugiere claves y valores al editar `interfaces.yaml`/`interfaces.example.yaml`. Si abres el archivo suelto sin la carpeta del repo como workspace, la cabecera `# yaml-language-server: $schema=./<módulo>.schema.json` que llevan los `.example.yaml` generados también lo activa por su cuenta.

## Modelos YANG preparados pero no conectados

`device/yang/sistema/` (`ietf-system`, RFC 7317) y `device/yang/plataforma/` (`openconfig-platform`) ya están en el repo con sus dependencias completas, y `scripts/generate_config.py` les genera `device/init/sistema/sistema.example.yaml` y `device/init/plataforma/openconfig-platform.example.yaml` con schema para autocompletar. Pero **ninguno de los dos hace nada todavía dentro del lab**:

- `device/entrypoint.py` no los instala con `sysrepoctl -i` (solo instala `iana-if-type`, `sandbox-device` y `sandbox-if-ext`).
- No hay ningún seed cargado para ellos en `seed_datastores()`.
- No hay callbacks en `device/netconf_lab/` sirviendo su estado operacional ni sus RPCs.

Dos detalles a tener en cuenta si los retomas:

- `sistema.example.yaml` mezcla **dos** módulos porque `ietf-system` importa `ietf-netconf-acm` (para anotar el leaf `password` como sensible) y ese módulo trae su propio árbol de configuración (`nacm:`) — el generador lo vuelca también, aunque no lo hayas pedido.
- `openconfig-platform.example.yaml` es casi todo huecos: el modelo es mayormente `config false` (el inventario de componentes lo publica el propio dispositivo), así que el "ejemplo editable" no aporta gran cosa hasta que haya un callback de datos operacionales detrás — sería el reemplazo natural del inventario virtual actual que vive en `sandbox-device`.

## Prueba automática

```bash
./scripts/smoke-test.sh
```

La prueba levanta el laboratorio y verifica lectura, edición, estado de interfaz y RPC.

## Estructura

```text
.
├── compose.yml                  # desarrollo: build local de device/
├── compose.prod.yml             # producción: pull de ghcr.io/nonetss/netconf-lab
├── .github/workflows/
│   └── docker-build.yml         # smoke test + publish a GHCR en push a main
├── device
│   ├── Dockerfile
│   ├── entrypoint.py
│   ├── netconf_lab/
│   │   ├── __main__.py          # bootstrap: loop, señales, conexión sysrepo
│   │   ├── logging_conf.py
│   │   ├── state.py             # uptime/boot-time compartido
│   │   ├── subscriptions.py     # cableado sess.subscribe_*
│   │   ├── interfaces/          # todo ietf-interfaces
│   │   │   ├── kernel.py        # reconciliación con el Linux del contenedor
│   │   │   └── oper.py
│   │   └── system/              # todo sandbox-device
│   │       ├── oper.py
│   │       └── rpc.py
│   ├── init/
│   │   ├── interfaz/
│   │   │   ├── interfaces.yaml          # seed real, cargado en el primer arranque
│   │   │   ├── interfaces.example.yaml  # generado, solo de referencia
│   │   │   └── interfaces.schema.json   # generado, para autocompletado
│   │   └── yaml_to_json.py      # convierte el YAML de arriba a JSON para sysrepocfg
│   └── yang/
│       └── interfaz/            # ietf-interfaces + ietf-ip + iana-if-type + tipos
├── scripts/
│   ├── generate_config.py       # device/yang/<feature>/ -> device/init/<feature>/*.example.yaml + *.schema.json
│   └── smoke-test.sh
```

## Base técnica

Netopeer2 implementa el servidor NETCONF sobre libyang/libnetconf2 y usa Sysrepo como datastore. El proyecto fija la imagen `sysrepo/netopeer2` por digest para evitar que una reconstrucción cambie silenciosamente; puedes sustituirla mediante `NETOPEER2_IMAGE`.
