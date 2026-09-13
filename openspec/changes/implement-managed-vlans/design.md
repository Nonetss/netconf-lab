## Context

El dispositivo instala módulos y semillas desde directorios por feature y el plugin Python ya se suscribe a cambios de `ietf-interfaces`, crea enlaces `dummy` y obtiene su estado con `ip -j`. No existe aún un modelo VLAN ni una abstracción de plano de datos de capa 2. Véanse `proposal.md` y las especificaciones delta para la motivación y el contrato.

## Goals / Non-Goals

**Goals:**
- Incorporar `ieee802-dot1q-bridge`, `ieee802-dot1q-types`, `ieee802-types` y sus dependencias IETF, anunciándolos como capacidades NETCONF.
- Unificar la reconciliación de interfaces y VLANs en un plano de datos Linux reproducible, con bridge filtering 802.1Q.
- Validar semántica access/trunk, eliminación y aislamiento en una prueba automatizada, además de exponer estado operacional.

**Non-Goals:**
- Implementar enrutamiento inter-VLAN, protocolos de routing, ACLs, STP/LACP, QoS, DHCP o servicios de gateway; el dispositivo se comportará como switch gestionado de capa 2 para esta entrega.
- Crear o modificar módulos YANG propios, aplicar cambios a interfaces del host o gestionar `eth0`/`lo`.
- Simular telemetría de hardware más allá del estado que Linux puede informar.

## Decisions

### Usar IEEE 802.1Q Bridge como contrato VLAN

Se instalarán los módulos oficiales `ieee802-dot1q-bridge`, `ieee802-dot1q-types` e `ieee802-types`, junto con una copia aislada de las dependencias IETF de interfaces. `bridge-port` aporta la asociación y PVID del puerto; `filtering-database/vlan-registration-entry/port-map` representa las membresías y si cada transmisión es etiquetada o sin etiqueta.

Se descartan módulos propios, específicos de fabricante y OpenConfig VLAN/network-instance. El modelo IEEE contiene configuración NETCONF editable para bridge ports, PVID y VLAN Registration Entries.

### Representar la conmutación mediante un bridge Linux con VLAN filtering

El reconciliador mantendrá un bridge privado del laboratorio con `vlan_filtering=1`. Cada interfaz dummy que tenga configuración conmutada se conectará al bridge y sus reglas se expresarán mediante `bridge vlan`: PVID y salida sin etiqueta para access, y VLAN nativa/PVID más VLANs etiquetadas para trunk. La sincronización calculará el estado deseado completo y retirará primero reglas, puertos y VLANs obsoletos.

Esta elección usa el forwarding 802.1Q real del kernel y preserva aislamiento sin implementar un switch en Python. Crear bridges separados por VLAN simplificaría el caso access, pero no representa trunks correctamente ni permite una VLAN nativa.

### Validar referencias antes de aplicar cambios al kernel

La reconciliación valida que los `port-ref` apunten a bridge ports administrados, que el PVID figure en su port-map y que su entrada sea `untagged`; los puertos protegidos no reciben configuración conmutada. El laboratorio numera port-ref desde 1 ordenando los nombres de los bridge ports para mantener una asignación reproducible.

La alternativa de ignorar membresías inválidas deja `running` divergente del plano de datos y no cumple la atomicidad esperada de una operación NETCONF.

### Estado operacional derivado de la configuración y del kernel

El callback operacional de VLAN combinará los objetos configurados con `bridge -j vlan show` y `ip -j link show`. Informará VLANs y membresías efectivas y marcará como no operativo un puerto sin enlace o no activo. El callback de interfaces conservará su comportamiento existente y reflejará el master bridge donde corresponda.

No se guardará una segunda copia de estado VLAN: Sysrepo contiene el deseo configurado y el kernel es la fuente de la efectividad.

### Semilla y prueba de humo aisladas

Se añadirá una topología semilla mínima con al menos una VLAN y puertos dummy. El smoke test configurará VLANs y puertos con `sysrepocfg`, esperará a la reconciliación y verificará reglas con `bridge vlan show` y el datastore operacional. Para comprobar aislamiento de forwarding, creará pares `veth` y namespaces efímeros dentro del contenedor o usará contadores/paquetes Ethernet equivalentes; el test limpiará sus recursos.

## Risks / Trade-offs

- [El módulo OpenConfig y la versión instalada de `ietf-interfaces` pueden tener imports o augments incompatibles] → Validar el conjunto completo con `pyang` y una imagen limpia antes de generar semillas.
- [La imagen base podría no incluir utilidades bridge completas o privilegios `NET_ADMIN`] → Verificar `bridge vlan` en el contenedor y documentar/ajustar el servicio Compose con la capacidad mínima requerida.
- [Un fallo parcial de comandos `ip`/`bridge` puede dejar el plano de datos desincronizado] → Aplicar una reconciliación idempotente de estado deseado completo y propagar el error para abortar la transacción.
- [Asignar IPv4 a un puerto bridgeado no proporciona por sí solo una SVI] → Mantener IP de interfaces fuera del alcance VLAN y documentar que el routing inter-VLAN requerirá una capacidad posterior.
- [Las semillas se reaplican en cada arranque] → Hacer la topología seed idempotente y comprobar que una reconstrucción sin borrar volumen converge al mismo bridge y membresías.

## Migration Plan

1. Construir e iniciar con volumen nuevo para instalar los módulos YANG, generar y cargar las semillas.
2. Ejecutar el smoke test de interfaces y VLANs; confirmar las capacidades NETCONF y el estado operacional.
3. Para instalaciones existentes, reconstruir e iniciar; las semillas se reaplican y el reconciliador converge. Si Sysrepo no acepta el esquema por una revisión instalada previamente, ejecutar `docker compose down -v --remove-orphans` y volver a iniciar.
4. Para revertir, retirar la configuración VLAN, reconstruir la versión anterior y eliminar el bridge y los puertos administrados por el laboratorio; si se requiere descartar el esquema instalado, recrear el volumen.
