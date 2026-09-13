## Purpose

Permitir que el laboratorio simule un dispositivo Ethernet gestionado con VLANs 802.1Q, puertos access y trunk, y estado operacional consultable por NETCONF.

## ADDED Requirements

### Requirement: Configuración de VLANs estándar
El dispositivo SHALL exponer la configuración de VLAN mediante los modelos YANG OpenConfig estándar instalados en el dispositivo. SHALL admitir una VLAN con identificador entre 1 y 4094, nombre y estado administrativo, y rechazará una configuración que no satisfaga las restricciones del modelo.

#### Scenario: Creación de una VLAN habilitada
- **WHEN** un cliente NETCONF crea la VLAN 100 con nombre y estado habilitado
- **THEN** la VLAN queda presente en `running` y `startup` con los valores configurados

#### Scenario: Identificador de VLAN inválido
- **WHEN** un cliente NETCONF intenta configurar un identificador fuera del rango admitido por el modelo
- **THEN** la operación es rechazada sin modificar la configuración efectiva

### Requirement: Asignación de puertos VLAN
El dispositivo SHALL permitir configurar en interfaces gestionables el modo `access` con una VLAN sin etiquetar, o el modo `trunk` con una VLAN nativa y una lista de VLANs etiquetadas. SHALL rechazar una pertenencia que haga referencia a una VLAN no configurada y SHALL impedir que una interfaz protegida se convierta en puerto VLAN.

#### Scenario: Puerto de acceso
- **WHEN** un cliente asigna una interfaz dummy a la VLAN 100 en modo `access`
- **THEN** el tráfico no etiquetado recibido por ese puerto pertenece exclusivamente a la VLAN 100

#### Scenario: Puerto troncal
- **WHEN** un cliente asigna una interfaz dummy a un trunk con VLAN nativa 100 y VLAN permitida 200
- **THEN** el tráfico de la VLAN 100 se trata como no etiquetado en el puerto y el de la VLAN 200 como etiquetado

#### Scenario: VLAN ausente
- **WHEN** un cliente intenta asignar un puerto a una VLAN que no existe
- **THEN** la transacción NETCONF es rechazada y la membresía anterior permanece sin cambios

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
