## Context

La propuesta documenta capacidades que ya están implementadas y repartidas entre el arranque del contenedor, los callbacks de Sysrepo, las semillas YAML y el smoke test. La fuente de verdad de configuración es `device/init/`; los cambios de configuración realizados manualmente en caliente se reemplazan por esa fuente durante el siguiente arranque.

## Goals / Non-Goals

**Goals:**
- Convertir el comportamiento ya observable en requisitos normativos y verificables.
- Separar los contratos de bootstrap, configuración, reconciliación y datos operacionales.
- Mantener la documentación independiente de detalles internos que puedan refactorizarse.

**Non-Goals:**
- Cambiar el protocolo NETCONF, los modelos YANG o los datos de las semillas.
- Implementar RPCs de `ietf-system` ni nuevos callbacks.
- Convertir el laboratorio en un router o alterar interfaces del host.

## Decisions

### Una capacidad única orientada al dispositivo

La especificación agrupa el comportamiento bajo `netconf-lab-device`, porque sus partes forman un único dispositivo consumido por clientes NETCONF y no existen capacidades OpenSpec previas que separar. Los requisitos individuales preservan los límites funcionales.

Alternativa considerada: crear especificaciones independientes por módulo YANG. Se descarta porque el ciclo de arranque y las semillas son transversales y una especificación fragmentada ocultaría sus dependencias operativas.

### Escenarios basados en efectos externos

Los escenarios verifican datastores, enlaces visibles en el contenedor y respuestas operacionales, sin mencionar clases ni funciones Python. Esto permite cambiar la implementación de los callbacks sin romper el contrato.

Alternativa considerada: describir las suscripciones y bucles internos. Se descarta porque son decisiones de implementación.

### Semillas reaplicadas en cada arranque

El contrato declara la reaplicación de YAML y la copia a `startup`, ya que es la condición que hace reproducible el laboratorio con un volumen persistente. La semántica es una fusión, no un reemplazo total del datastore.

Alternativa considerada: sembrar solo en la primera inicialización. Se descarta porque impediría aplicar cambios de las semillas cuando el volumen ya existe.

## Risks / Trade-offs

- [La documentación existente puede describir capacidades anteriores] → La especificación se basa en los callbacks y el arranque actualmente versionados; futuras actualizaciones del README deberán alinearse con ella.
- [La aplicación de semillas sobrescribe cambios manuales al reiniciar] → Se declara explícitamente como comportamiento esperado y se conserva el YAML como fuente de verdad.
- [Los enlaces virtuales podrían confundirse con interfaces reales] → Los requisitos limitan el efecto al contenedor y protegen `eth0` y `lo`.

## Migration Plan

1. Revisar los artefactos de esta propuesta frente al comportamiento actual.
2. Actualizar la documentación de usuario que contradiga los requisitos aprobados.
3. Ejecutar el smoke test para confirmar los escenarios de interfaz ya cubiertos.
4. No se requiere migración ni rollback de datos, porque este cambio solo añade documentación de planificación.
