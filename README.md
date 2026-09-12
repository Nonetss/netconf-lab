# Sandbox NETCONF con Docker Compose

Laboratorio autocontenido que simula un dispositivo de red, no sólo un socket que responde. Usa **Netopeer2** como servidor NETCONF, **Sysrepo** como datastore YANG, `ietf-interfaces` + `ietf-ip`, un modelo `sandbox-device`, estado operacional dinámico y RPCs.

## Para qué sirve

Un target NETCONF real (config + estado + RPCs sobre datastores de verdad) contra el que probar cosas sin tocar hardware ni un router de producción:

- Aprender o enseñar NETCONF/YANG con `netopeer2-cli` o cualquier cliente, sin depender de acceso a un dispositivo físico.
- Desarrollar y probar clientes/automatización NETCONF (scripts propios, colecciones Ansible, gateways RESTCONF, etc.) contra un servidor que reacciona de verdad — activar `ge1` mueve una interfaz `dummy` real dentro del contenedor.
- Usarlo como dependencia de integración en CI para herramientas que hablan NETCONF (así se usa en `.github/workflows/docker-build.yml`, ver `scripts/smoke-test.sh`).
- Diseñar tu propio modelo YANG y aprender a cablear config/estado/RPCs a un backend real, partiendo de `sandbox-device` como ejemplo mínimo.

## Qué simula

- NETCONF sobre SSH en TCP/830.
- Datastores `running`, `startup` y `candidate`.
- Interfaces `ge0`, `ge1` y `lo0` configurables con `ietf-interfaces`/`ietf-ip`.
- Interfaces Linux `dummy` reales dentro del namespace del contenedor; `enabled`, MTU y direcciones IPv4 se reconcilian desde la configuración YANG.
- Estado operacional: `oper-status`, MAC, índice, velocidad y contadores de tráfico.
- Sistema: hostname, ubicación, versión, serial, uptime, CPU y memoria.
- Inventario virtual de chasis, control plane, ventilador y fuente.
- RPCs de laboratorio: `ping` y `reboot` simulado.
- Persistencia del datastore en un volumen Docker.

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

1. Copia el `.yang` a `device/yang/`.
2. Añade en `device/entrypoint.py` un `sysrepoctl -i` idempotente.
3. Añade datos iniciales en `device/init/` como YAML si son necesarios (se convierten a JSON y se cargan vía `sysrepocfg` en el primer arranque, ver `device/init/yaml_to_json.py`).
4. Implementa callbacks en `device/netconf_lab/` para nodos `config false` (`interfaces/oper.py`, `system/oper.py`), RPCs (`system/rpc.py`) o acciones.
5. Reconstruye y reinicia el volumen si cambió el esquema: `docker compose down -v && docker compose up --build -d`.

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
│   │   ├── interfaces.yaml
│   │   ├── system.yaml
│   │   └── yaml_to_json.py      # convierte el YAML de arriba a JSON para sysrepocfg
│   └── yang/sandbox-device.yang
└── scripts/smoke-test.sh
```

## Base técnica

Netopeer2 implementa el servidor NETCONF sobre libyang/libnetconf2 y usa Sysrepo como datastore. El proyecto fija la imagen `sysrepo/netopeer2` por digest para evitar que una reconstrucción cambie silenciosamente; puedes sustituirla mediante `NETOPEER2_IMAGE`.
