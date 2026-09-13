## MODIFIED Requirements

### Requirement: Reconciliación de interfaces virtuales

El dispositivo SHALL reconciliar las interfaces configuradas mediante `ietf-interfaces` con enlaces Linux `dummy` dentro del contenedor. Para nombres válidos que no sean interfaces protegidas, SHALL crear el enlace si no existe y reflejar los valores configurados de estado administrativo, MTU y direcciones IPv4. SHALL no modificar `eth0` ni `lo`. Cuando una interfaz tenga `ieee802-dot1q-bridge:bridge-port`, SHALL reconciliarla como puerto de conmutación en el plano de datos VLAN y conservar su configuración IPv4 sin cambios.

#### Scenario: Creación de una interfaz dummy activada

- **WHEN** un cliente configura una interfaz válida nueva con `enabled` en `true`
- **THEN** el contenedor crea el enlace `dummy` correspondiente y lo deja en estado UP

#### Scenario: Protección de enlaces base

- **WHEN** la configuración incluye `eth0` o `lo`
- **THEN** el reconciliador no crea, elimina ni altera esos enlaces Linux

#### Scenario: Interfaz configurada como puerto VLAN

- **WHEN** un cliente configura una interfaz dummy existente como `bridge-port` IEEE con PVID y port-map
- **THEN** el reconciliador conserva el enlace dummy y aplica su pertenencia VLAN efectiva
