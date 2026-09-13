## 1. Modelos IEEE y configuración inicial

- [x] 1.1 Descargar `ieee802-dot1q-bridge`, `ieee802-dot1q-types`, `ieee802-types` y dependencias IETF en una feature aislada; verificar todos los imports y augments con `uv run --with pyang`.
- [x] 1.2 Regenerar los YAML de ejemplo y JSON Schema con `uv run --with pyang python3 scripts/generate_config.py`; verificar que se generan para el modelo IEEE sin modificar semillas reales.
- [ ] 1.3 Crear una semilla VLAN mínima con VLANs y puertos dummy access/trunk; verificar que una imagen nueva instala los módulos y carga la semilla en `running` y `startup`.

## 2. Plano de datos VLAN

- [ ] 2.1 Añadir la abstracción idempotente para inspeccionar y reconciliar un bridge Linux privado con `vlan_filtering=1`; verificar creación, convergencia tras reinicio y eliminación de recursos administrados.
- [ ] 2.2 Extender la suscripción de Sysrepo para leer `bridge-port`/PVID y `vlan-registration-entry`/`port-map` IEEE; verificar que una edición NETCONF válida aplica el bridge, PVID y las VLANs etiquetadas configuradas.
- [ ] 2.3 Implementar validación transaccional de referencias a VLAN, modos access/trunk y puertos protegidos; verificar que una edición inválida se rechaza y que las reglas de kernel previas no cambian.
- [ ] 2.4 Integrar la reconciliación VLAN con el ciclo existente de interfaces dummy; verificar que `eth0` y `lo` no se unen al bridge y que eliminar o deshabilitar un puerto retira sus reglas.

## 3. Estado operacional

- [ ] 3.1 Implementar el callback operacional IEEE de VLAN a partir de `bridge -j vlan show` e `ip -j link show`; verificar que expone VLANs, puertos efectivos y estados no operativos para enlaces ausentes.
- [ ] 3.2 Mantener coherente el estado operacional de `ietf-interfaces` para interfaces bridgeadas; verificar que consultas operacionales de interfaces y VLAN no divergen del estado del kernel.

## 4. Imagen, documentación y validación integral

- [ ] 4.1 Confirmar que la imagen y Docker Compose incluyen `bridge` y las capacidades de red requeridas; verificar `bridge vlan show` dentro de un contenedor recién creado.
- [ ] 4.2 Ampliar `scripts/smoke-test.sh` con creación NETCONF de VLAN, puertos access y trunk, y comprobación de reglas y estado operacional; verificar que falla cuando falta una membresía o se asigna una VLAN inexistente.
- [ ] 4.3 Añadir al smoke test una comprobación reproducible de forwarding dentro de una VLAN y aislamiento entre VLANs usando recursos efímeros; verificar limpieza de los recursos al terminar.
- [ ] 4.4 Actualizar README y CLAUDE.md con capacidades, modelo, límites de capa 2 y comandos de inspección VLAN; verificar que los ejemplos corresponden con las rutas YANG instaladas.
- [ ] 4.5 Ejecutar `ruff check .`, `./scripts/smoke-test.sh` y `openspec validate implement-managed-vlans --strict`; verificar que todos finalizan correctamente.
