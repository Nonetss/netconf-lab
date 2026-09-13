# managed-vlans Specification

## Purpose

Permitir que el laboratorio simule un dispositivo Ethernet gestionado con VLANs IEEE 802.1Q y estado operacional consultable por NETCONF.

## Requirements

### Requirement: Configuración de VLANs estándar
El dispositivo SHALL exponer la configuración mediante `ieee802-dot1q-bridge`, con un bridge cliente VLAN, componente C-VLAN, `bridge-port`/PVID y `filtering-database/vlan-registration-entry/port-map`. SHALL rechazar VIDs fuera de 1..4094 para el plano de datos Linux.

#### Scenario: Creación de una VLAN habilitada
- **WHEN** un cliente NETCONF registra el VID 100 en un `vlan-registration-entry` estático
- **THEN** la entrada queda presente en `running` y `startup`

#### Scenario: Identificador de VLAN inválido
- **WHEN** un cliente NETCONF intenta configurar un identificador fuera del rango admitido por el modelo
- **THEN** la operación es rechazada sin modificar la configuración efectiva

### Requirement: Asignación de puertos VLAN
El dispositivo SHALL permitir configurar interfaces gestionables como `bridge-port`, asignar su PVID y registrar membresías en el `port-map`. Una entrada `vlan-transmitted: untagged` SHALL coincidir con el PVID; una entrada `tagged` SHALL transmitir el VID etiquetado. SHALL impedir que una interfaz protegida se convierta en puerto VLAN.

#### Scenario: Puerto de acceso
- **WHEN** un cliente asigna el PVID 100 a una interfaz dummy y registra el VID 100 como `untagged`
- **THEN** el tráfico no etiquetado recibido por ese puerto pertenece exclusivamente a la VLAN 100

#### Scenario: Puerto troncal
- **WHEN** un cliente asigna PVID 100 a una interfaz dummy y registra 100 como `untagged` y 200 como `tagged`
- **THEN** el tráfico de la VLAN 100 se trata como no etiquetado en el puerto y el de la VLAN 200 como etiquetado

#### Scenario: PVID reservado
- **WHEN** un cliente intenta configurar el PVID 4095
- **THEN** la operación es rechazada sin modificar la configuración efectiva

### Requirement: Conmutación VLAN aislada
El dispositivo SHALL aplicar las membresías configuradas para que los puertos de una misma VLAN puedan conmutar tráfico Ethernet entre sí y los puertos de VLANs distintas permanezcan aislados. SHALL retirar del plano de datos una membresía, una VLAN o un puerto que se elimine o se deshabilite.

#### Scenario: Aislamiento entre VLANs
- **WHEN** existen puertos de acceso separados en las VLANs 100 y 200
- **THEN** no existe reenvío de capa 2 entre ambos puertos

#### Scenario: Eliminación de VLAN
- **WHEN** un cliente elimina una VLAN configurada
- **THEN** el dispositivo elimina sus membresías efectivas y deja de conmutar tráfico para esa VLAN

### Requirement: Estado operacional VLAN
El datastore operacional SHALL informar para cada VLAN configurada su identificador, nombre, estado y los puertos con membresía efectiva. SHALL reflejar que una VLAN o un puerto no están operativos cuando no exista o no esté activo el recurso Linux correspondiente.

#### Scenario: Consulta de estado VLAN
- **WHEN** un cliente consulta el datastore operacional después de configurar una VLAN y sus puertos
- **THEN** la respuesta incluye la VLAN y las membresías efectivas de sus interfaces

#### Scenario: Puerto ausente
- **WHEN** una interfaz configurada como puerto VLAN no tiene un enlace Linux presente
- **THEN** el estado operacional de su membresía informa que el puerto no está operativo
