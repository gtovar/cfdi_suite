# Documentación del repositorio

Este directorio concentra documentación persistente del producto, del motor CFDI y del flujo de trabajo.

## Orden recomendado de lectura

Si vienes por primera vez al repo:

1. [../README.md](../README.md)
2. [arquitectura.md](./arquitectura.md)
3. [cfdi-ui-dictionary.md](./cfdi-ui-dictionary.md)
4. [roadmap/cfdi-engine-migration/index.md](./roadmap/cfdi-engine-migration/index.md)

Si vienes a trabajar con agentes o sesiones guiadas por IA:

1. [ai/workflow.md](./ai/workflow.md)
2. [ai/implementation-policy.md](./ai/implementation-policy.md)
3. [ai/ui-testing-baseline.md](./ai/ui-testing-baseline.md)
4. [ai/templates/](./ai/templates/)

## Mapa de documentos

### Producto y dominio

- [arquitectura.md](./arquitectura.md): vista de alto nivel del sistema, capas y flujo de análisis
- [cfdi-ui-dictionary.md](./cfdi-ui-dictionary.md): definición de términos y reglas de interpretación UI

### Decisiones

- [analysis/2026-04-17-python-satcfdi-decision.md](./analysis/2026-04-17-python-satcfdi-decision.md): decisión base sobre el futuro del motor CFDI
- [analysis/2026-04-18-python-backend-platform-decision.md](./analysis/2026-04-18-python-backend-platform-decision.md): reapertura hacia arquitectura frontend + backend Python

### Roadmap del motor

- [roadmap/cfdi-engine-migration/index.md](./roadmap/cfdi-engine-migration/index.md): índice y secuencia de migración
- [roadmap/cfdi-engine-migration/STATUS.md](./roadmap/cfdi-engine-migration/STATUS.md): estado corto y próxima acción
- [roadmap/python-backend-platform/index.md](./roadmap/python-backend-platform/index.md): nueva ruta estratégica hacia backend Python
- [roadmap/python-backend-platform/STATUS.md](./roadmap/python-backend-platform/STATUS.md): estado corto de la nueva ruta

### Flujo de trabajo asistido por IA

- [ai/workflow.md](./ai/workflow.md): contrato de tipos de tarea
- [ai/implementation-policy.md](./ai/implementation-policy.md): reglas de ejecución
- [ai/ui-testing-baseline.md](./ai/ui-testing-baseline.md): base de validación UI
- [ai/pilots/README.md](./ai/pilots/README.md): historial de pilotos previos

## Regla de mantenimiento

Cada documento debe tener una responsabilidad clara:

- `README.md`: onboarding y uso rápido
- `docs/arquitectura.md`: estructura estable del sistema
- `docs/analysis/`: decisiones o comparativas fechadas
- `docs/roadmap/`: secuencias de trabajo vivas
- `docs/ai/`: operación de agentes y ejecución asistida

No conviertas `README.md` en bitácora. Si un cambio afecta contratos o dirección, actualiza el documento temático correcto y deja el `README` como punto de entrada.
