## Why

El laboratorio ya ofrece más capacidades de las que una especificación formal describe: instala modelos YANG y semillas de forma genérica, reconcilia interfaces Linux y sirve estado operacional para interfaces, sistema y plataforma. Documentar ese comportamiento como contrato facilita mantenerlo y verificar cambios futuros.

## What Changes

- Documentar el comportamiento observable del dispositivo NETCONF simulado.
- Establecer los requisitos de descubrimiento e instalación de módulos YANG, carga de semillas YAML y persistencia de los datastores.
- Especificar la reconciliación segura de interfaces configuradas con `ietf-interfaces` contra enlaces `dummy` del contenedor y su estado operacional.
- Especificar los datos operacionales que se exponen para `ietf-system` y `openconfig-platform`.
- Añadir tareas de verificación documental y de smoke test; no se modifica el comportamiento de ejecución existente.

## Capabilities

### New Capabilities
- `netconf-lab-device`: Contrato funcional del dispositivo NETCONF simulado, sus modelos, semillas, reconciliación y estado operacional.

### Modified Capabilities

Ninguna.

## Impact

- Documentación y planificación en OpenSpec.
- Comportamiento documentado en `device/entrypoint.py` y `device/netconf_lab/`.
- Configuración de origen en `device/yang/` y `device/init/`.
- Cobertura de integración en `scripts/smoke-test.sh`.
