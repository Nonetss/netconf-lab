## Purpose

Define el contrato observable del dispositivo NETCONF virtual para que clientes y mantenedores puedan configurarlo y consultar su estado de forma reproducible.

## ADDED Requirements

### Requirement: Arranque reproducible del dispositivo NETCONF
El laboratorio SHALL exponer un servidor NETCONF sobre SSH y los datastores `running`, `startup` y `candidate` al iniciar el servicio `device`. Las credenciales y el puerto SHALL poder configurarse mediante los mecanismos documentados de Docker Compose.

#### Scenario: Servicio saludable tras el arranque
- **WHEN** se inicia el servicio con Docker Compose
- **THEN** el contenedor alcanza un estado saludable y acepta conexiones NETCONF en el puerto configurado

### Requirement: Descubrimiento de modelos y semillas
El dispositivo SHALL descubrir los archivos YANG ubicados en cada `device/yang/<feature>/` e instalar los módulos que Sysrepo aún no conozca, activando sus características declaradas. En cada inicio SHALL convertir y aplicar todos los `device/init/<feature>/*.yaml`, excluyendo los archivos `*.example.yaml`, sobre `running` y copiar el resultado a `startup`.

#### Scenario: Una nueva semilla se aplica sin eliminar el volumen
- **WHEN** se añade o modifica un archivo de semilla YAML y se reconstruye e inicia el servicio conservando `sysrepo-data`
- **THEN** sus valores se fusionan en `running` durante el siguiente arranque y están disponibles también en `startup`

#### Scenario: Los ejemplos generados no se cargan como configuración
- **WHEN** una carpeta de inicialización contiene un archivo terminado en `.example.yaml`
- **THEN** el archivo no modifica ningún datastore

### Requirement: Reconciliación de interfaces virtuales
El dispositivo SHALL reconciliar las interfaces configuradas mediante `ietf-interfaces` con enlaces Linux `dummy` dentro del contenedor. Para nombres válidos que no sean interfaces protegidas, SHALL crear el enlace si no existe y reflejar los valores configurados de estado administrativo, MTU y direcciones IPv4. SHALL no modificar `eth0` ni `lo`.

#### Scenario: Creación de una interfaz dummy activada
- **WHEN** un cliente configura una interfaz válida nueva con `enabled` en `true`
- **THEN** el contenedor crea el enlace `dummy` correspondiente y lo deja en estado UP

#### Scenario: Protección de enlaces base
- **WHEN** la configuración incluye `eth0` o `lo`
- **THEN** el reconciliador no crea, elimina ni altera esos enlaces Linux

### Requirement: Estado operacional de interfaces
El dispositivo SHALL publicar datos operacionales de cada interfaz configurada, incluidos estados administrativo y operacional, dirección física, índice, velocidad y contadores de tráfico. El estado SHALL indicar `not-present` cuando no exista un enlace Linux para una interfaz configurada.

#### Scenario: Consulta de estado de una interfaz creada
- **WHEN** una interfaz configurada tiene un enlace `dummy` activo
- **THEN** una consulta al datastore operacional devuelve su `oper-status` y sus contadores

### Requirement: Estado operacional de sistema y plataforma
El dispositivo SHALL publicar para `ietf-system` el sistema operativo del contenedor y las marcas temporales actual y de arranque. Para cada componente configurado de `openconfig-platform`, SHALL publicar su identidad, tipo, descripción e identificadores virtuales deterministas.

#### Scenario: Consulta del estado de sistema
- **WHEN** un cliente solicita `/ietf-system:system-state`
- **THEN** la respuesta incluye plataforma, fecha actual y fecha de arranque

#### Scenario: Consulta del inventario de plataforma
- **WHEN** un cliente solicita los componentes de `openconfig-platform`
- **THEN** cada componente configurado contiene un bloque `state` con nombre, tipo y número de serie virtual
