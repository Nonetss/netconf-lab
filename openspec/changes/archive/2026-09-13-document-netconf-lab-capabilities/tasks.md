## 1. Alineación documental

- [x] 1.1 Revisar `README.md` y actualizar las secciones que aún limiten el estado operacional dinámico a interfaces; verificar que describe `ietf-system` y `openconfig-platform` conforme a la especificación.
- [x] 1.2 Revisar `CLAUDE.md` para que las instrucciones de arquitectura y arranque coincidan con el contrato `netconf-lab-device`; verificar que no contradiga las semillas reaplicadas ni las interfaces protegidas.

## 2. Verificación de integración

- [ ] 2.1 Ejecutar `./scripts/smoke-test.sh` y verificar creación, activación y datos operacionales de una interfaz `dummy`.
- [ ] 2.2 Añadir o ejecutar comprobaciones de consulta operacional para `ietf-system` y `openconfig-platform`; verificar que devuelven respectivamente plataforma/relojes y el estado de cada componente sembrado.
- [ ] 2.3 Validar que una reconstrucción con `sysrepo-data` conservado reaplica las semillas YAML y excluye los archivos `.example.yaml`; verificar los datastores `running` y `startup`.
