# Sandbox NETCONF con Docker Compose

Laboratorio autocontenido que simula un dispositivo de red, no sólo un socket que responde. Usa **Netopeer2** como servidor NETCONF, **Sysrepo** como datastore YANG, `ietf-interfaces` + `ietf-ip`, un modelo `sandbox-device`, estado operacional dinámico, RPCs y un cliente Python con `ncclient`.

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

Requisitos: Docker Engine/Desktop con Compose v2. La imagen base publicada es `linux/amd64`; Compose fija esa plataforma, por lo que en Apple Silicon/ARM se ejecutará mediante emulación.

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

## Probar con Python

```bash
# Capacidades, running y estado operacional
docker compose exec client python examples/get_all.py

# Cambiar hostname
docker compose exec client python examples/edit_hostname.py router-zrh-01

# Activar o desactivar ge1; el cambio llega a la interfaz Linux dummy
docker compose exec client python examples/toggle_interface.py ge1 true

# Ejecutar el RPC YANG ping
docker compose exec client python examples/rpc_ping.py 127.0.0.1
```

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
2. Añade en `device/entrypoint.sh` un `sysrepoctl -i` idempotente.
3. Añade datos iniciales XML en `device/init/` si son necesarios.
4. Implementa callbacks en `device/app/device_plugin.py` para nodos `config false`, RPCs o acciones.
5. Reconstruye y reinicia el volumen si cambió el esquema: `docker compose down -v && docker compose up --build -d`.

## Prueba automática

```bash
make test
```

La prueba levanta el laboratorio y verifica lectura, edición, estado de interfaz y RPC.

## Estructura

```text
.
├── compose.yaml
├── device
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── app/device_plugin.py
│   ├── init/interfaces.xml
│   ├── init/system.xml
│   └── yang/sandbox-device.yang
├── client
│   ├── Dockerfile
│   └── examples/
├── scripts/smoke-test.sh
└── Makefile
```

## Base técnica

Netopeer2 implementa el servidor NETCONF sobre libyang/libnetconf2 y usa Sysrepo como datastore. El proyecto fija la imagen `sysrepo/netopeer2` por digest para evitar que una reconstrucción cambie silenciosamente; puedes sustituirla mediante `NETOPEER2_IMAGE`.
