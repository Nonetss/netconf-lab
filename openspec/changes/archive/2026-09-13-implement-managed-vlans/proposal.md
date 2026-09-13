## Why

El laboratorio permite crear interfaces virtuales, pero no representa el comportamiento de un dispositivo gestionado de capa 2: no se pueden definir dominios VLAN ni asignar puertos a ellos. Añadir VLANs estándar permite probar clientes NETCONF y automatizaciones contra una conmutación Ethernet aislada y observable, sin depender de hardware.

## What Changes

- Añadir la capacidad de configurar VLANs IEEE 802.1Q mediante `ieee802-dot1q-bridge`, sin modelos VLAN o network-instance OpenConfig.
- Modelar el bridge, sus componentes y los puertos con `bridge-port`/PVID y `filtering-database/vlan-registration-entry/port-map`.
- Reconciliar la configuración contra un bridge Linux con filtrado VLAN dentro del contenedor, sin modificar `eth0` ni `lo` ni las interfaces del host.
- Publicar estado operacional de las VLANs y de sus membresías para verificar la configuración efectiva.
- Sembrar una topología de ejemplo y ampliar la prueba de humo para validar aislamiento y configuración de VLAN.

## Capabilities

### New Capabilities
- `managed-vlans`: Configuración y estado operacional de VLANs 802.1Q y de sus puertos en el dispositivo virtual.

### Modified Capabilities
- `netconf-lab-device`: El dispositivo virtual pasa a comportarse también como conmutador Ethernet gestionado al reconciliar sus VLANs configuradas.

## Impact

- Nuevos módulos YANG IEEE 802.1Q y dependencias IETF aisladas bajo `device/yang/`.
- Nuevas semillas y esquemas YAML bajo `device/init/`.
- Plugin Python del dispositivo, especialmente la reconciliación y estado operacional de interfaces.
- Dependencias de sistema de la imagen para bridge VLAN filtering e inspección de estado.
- Documentación y `scripts/smoke-test.sh`.
