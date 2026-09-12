# Sandbox NETCONF con Docker Compose

Laboratorio autocontenido que simula un dispositivo de red, no sólo un socket que responde. Usa **Netopeer2** como servidor NETCONF, **Sysrepo** como datastore YANG y solo modelos **estándar**: `ietf-interfaces` + `ietf-ip`, `ietf-system`, `openconfig-platform` (RFC de IETF/IANA y OpenConfig, nada propio).

> `device/entrypoint.py` instala y siembra **cualquier cosa** que metas en `device/yang/<feature>/` + `device/init/<feature>/<módulo>.yaml` de forma genérica, sin tocar código — ver [Añadir modelos YANG](#añadir-modelos-yang). Lo único que sigue siendo manual es implementar callbacks Python para estado operacional (`config false`) o RPCs; hoy eso solo existe para `ietf-interfaces` (ver [Qué está de verdad conectado](#qué-está-de-verdad-conectado)).

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
- Config de sistema (`ietf-system`): hostname, ubicación, NTP, DNS, RADIUS, usuarios/claves SSH — sembrada, sirve datos reales por `sysrepocfg`/NETCONF.
- Inventario de chasis (`openconfig-platform`): chasis, control plane, ventilador, fuente, con propiedades y sub-componentes — también sembrado y consultable.
- Persistencia del datastore en un volumen Docker.

Lo que **no** hay todavía: RPCs (`ietf-system` trae `set-current-datetime`, `system-restart`... definidos en el YANG pero sin callback Python que los ejecute) y estado operacional dinámico fuera de interfaces (p.ej. uptime real de `ietf-system`, o que el inventario de `openconfig-platform` refleje algo más que lo sembrado). Eso requiere código en `device/netconf_lab/`, no solo YANG + seed — ver [Qué está de verdad conectado](#qué-está-de-verdad-conectado).

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

# Config de sistema (hostname, NTP, DNS...), sembrada desde device/init/sistema/sistema.yaml
docker compose exec device sysrepocfg -X -d running -m ietf-system -f xml

# Inventario de chasis, sembrado desde device/init/plataforma/openconfig-platform.yaml
docker compose exec device sysrepocfg -X -d running -m openconfig-platform -f xml
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

Copia `<módulo>.example.yaml` a `<módulo>.yaml` (ese es el que carga `sysrepocfg` **en cada arranque** — ver `device/init/yaml_to_json.py` y `device/entrypoint.py:seed_datastores`) y edítalo con VS Code:

1. Instala la extensión `redhat.vscode-yaml` (ya recomendada en `.vscode/extensions.json`).
2. Abre la carpeta del repo como workspace — `.vscode/settings.json` ya mapea `interfaces.yaml`/`interfaces.example.yaml` a su `schema.json` vía `yaml.schemas`. Si en vez de eso abres el archivo suelto, la cabecera `# yaml-language-server: $schema=./<módulo>.schema.json` que llevan los `.example.yaml` generados activa el mismo autocompletado sin depender del workspace.
3. `Ctrl+Espacio` en cualquier valor te sugiere lo que el YANG permite ahí — enums, booleanos, los `enum` de identities, etc.

### 5. El contenedor lo instala y siembra solo

`device/entrypoint.py` recorre `device/yang/` y `device/init/` en cada arranque, de forma genérica (no hay lista de módulos hardcodeada):

- **`install_modules()`**: por cada `.yang` de cada `device/yang/<feature>/` que `sysrepoctl -l` no conozca todavía, lo instala (`sysrepoctl -i <fichero> -s <carpeta-feature> -e '*' ...`, con **todas** las features del módulo activadas). Si netopeer2/sysrepo ya trae ese módulo de fábrica (pasa con `ietf-interfaces`, `ietf-ip`, `ietf-netconf-acm`...) lo detecta por nombre y no lo reinstala — así que tu copia local en `device/yang/` puede ir a una revisión distinta sin conflicto, solo se usa para las herramientas de `scripts/`.
- **`seed_datastores()`** (**en cada arranque**, no solo el primero — el volumen `sysrepo-data` sobrevive a un `--build`, así que un guardado "solo la primera vez" habría hecho invisible cualquier edición posterior): por cada `<feature>/<módulo>.yaml` bajo `device/init/` (nunca los `.example.yaml`), lo convierte a JSON y lo aplica con `sysrepocfg --edit` sin `-m` — el propio JSON ya lleva sus claves cualificadas por módulo (`"ietf-system:system":`, etc.), así que un fichero puede tocar más de un módulo a la vez sin que haga falta decírselo.

En la práctica: crea la carpeta, copia el `.example.yaml` a `<módulo>.yaml`, rellénalo, y `docker compose up --build -d` (sin `-v`: el seed se reaplica solo) — sin tocar `entrypoint.py` para nada, a menos que quieras servir estado operacional o RPCs de verdad (ver siguiente sección). Solo hace falta `down -v` cuando cambias la **estructura** de un `.yang` ya instalado (nuevo leaf, container...) sin subir su `revision` — sysrepo tiene el esquema congelado desde el primer install y `sysrepoctl -U` solo actualiza si la revisión cambió.

## Qué está de verdad conectado

La instalación + seed de config (paso 5 de arriba) es genérica y cubre **todo** lo que haya en `device/yang/`/`device/init/`. Lo que **no** es genérico — porque no hay forma de que lo sea sin más contexto sobre qué quieres simular — son los callbacks Python en `device/netconf_lab/` para nodos `config false` (estado operacional) y RPCs. Hoy eso solo existe para `ietf-interfaces` (`device/netconf_lab/interfaces/`: reconcilia contra interfaces Linux `dummy` reales, sirve `oper-status`/MAC/contadores). `ietf-system` (RPCs `set-current-datetime`, `system-restart`...; estado `platform`/`clock`) y `openconfig-platform` (inventario dinámico en vez de solo lo sembrado) no tienen callback — sus RPCs no responden y su estado operacional es lo que haya en `running`, nada más.

Un par de detalles del seed real de este repo si tocas `device/init/sistema/sistema.yaml` o `device/init/plataforma/openconfig-platform.yaml`:

- `sistema.yaml` mezcla **dos** módulos porque `ietf-system` importa `ietf-netconf-acm` (para anotar el leaf `password` como sensible) y ese módulo trae su propio árbol de configuración (`nacm:`) — el generador lo vuelca también en el mismo `.example.yaml`, aunque no lo hayas pedido. El NACM sembrado aquí es real y activo (controla quién puede hacer qué por NETCONF) — no es solo un adorno.
- Cuidado con los tipos que son `typedef` sobre un número (`inet:port-number`, `oc-types:percentage`...): tienen que ir sin comillas en el YAML (`port: 123`, no `port: "123"`) — si tu editor los cita, `sysrepocfg` falla al arrancar con "no matching subtype" o similar. El JSON Schema generado ya los tipa como `integer` para que el autocompletado no te empuje a citarlos.

## Prueba automática

```bash
./scripts/smoke-test.sh
```

La prueba levanta el laboratorio y verifica lectura de la config, creación/activación de una interfaz y estado operacional.

## Base técnica

Netopeer2 implementa el servidor NETCONF sobre libyang/libnetconf2 y usa Sysrepo como datastore. El proyecto fija la imagen `sysrepo/netopeer2` por digest para evitar que una reconstrucción cambie silenciosamente; puedes sustituirla mediante `NETOPEER2_IMAGE`.
