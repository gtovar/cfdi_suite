# cfdi_inspector

Inspector local de XML CFDI orientado a lectura operativa, extracción tabular y detección de discrepancias matemáticas y fiscales.

## Qué resuelve

`cfdi_inspector` convierte un XML CFDI en una vista legible para revisión manual. Hoy el producto está enfocado en dos perfiles:

- `ingreso`
- `pagos`

La app permite:

- detectar el perfil del CFDI
- parsear y normalizar el XML
- mostrar resumen del comprobante
- explicar campos fiscales clave con etiquetas humanas
- detectar hallazgos matemáticos y fiscales
- navegar conceptos impactados
- extraer tablas operativas para ingresos y pagos

## Qué no cubre hoy

El alcance actual es deliberadamente estrecho. No hay evidencia local de soporte completo para:

- nómina
- retenciones como flujo principal de producto
- validación XSD SAT exhaustiva
- render PDF o HTML
- integraciones con PAC o servicios SAT

## Inicio rápido

### Requisitos

- Node.js 20 o superior
- npm 10 o superior
- Python 3.11 o superior para la API local

### Instalación

```bash
npm install
```

### Variables de entorno

Actualmente la app no depende de variables de entorno para correr localmente. El archivo `.env.example` existe como remanente del template original y no es requerido para la inspección CFDI actual.

### Desarrollo

Backend:

```bash
pip install -r backend/requirements.txt
npm run dev:api
```

Frontend:

```bash
npm run dev
```

La app queda disponible en `http://localhost:3000`.
La API local queda disponible en `http://localhost:8000`.

### Validación

```bash
npm run lint
npm run test
npm run test:api
npm run build
```

## Uso básico

1. Abre la app en local.
2. Carga un XML CFDI desde la interfaz.
3. Revisa el resumen del comprobante y el veredicto.
4. Inspecciona hallazgos críticos o de revisión en el sidebar.
5. Navega conceptos impactados y auditoría de traslados.
6. Usa la tabla de extracción para revisar filas de ingresos o pagos.

## Scripts disponibles

- `npm run dev`: arranca Vite en `0.0.0.0:3000`
- `npm run dev:api`: arranca la API Python local en `0.0.0.0:8000`
- `npm run build`: genera el build de producción
- `npm run preview`: sirve el build localmente
- `npm run lint`: corre `tsc --noEmit`
- `npm run test`: ejecuta la suite con Vitest
- `npm run test:api`: ejecuta contract tests y service tests del backend Python
- `npm run clean`: elimina `dist/`

## Arquitectura del repo

La estructura principal está separada por producto, aplicación y dominio CFDI:

- `src/App.tsx`: shell principal de la experiencia de inspección
- `backend/app/`: API Python, contratos, services y providers
- `src/components/`: UI y navegación operativa
- `src/app/`: hooks y view-models del producto
- `src/cfdi/application/`: parsing, análisis y extracción
- `src/cfdi/domain/`: normalización, catálogos y diagnóstico matemático
- `src/cfdi/engine/`: contrato del motor y adaptación del motor actual TypeScript
- `src/cfdi/public/`: API pública consumible por UI o integraciones internas
- `src/lib/`: worker y cliente del worker para análisis fuera del hilo principal
- `docs/`: decisiones, roadmap y documentación operativa

Más detalle en [docs/arquitectura.md](docs/arquitectura.md).

## Documentación extendida

- [docs/README.md](docs/README.md): mapa de documentación del repo
- [docs/arquitectura.md](docs/arquitectura.md): capas, flujo y responsabilidades
- [docs/cfdi-ui-dictionary.md](docs/cfdi-ui-dictionary.md): semántica UI de campos CFDI
- [docs/analysis/2026-04-17-python-satcfdi-decision.md](docs/analysis/2026-04-17-python-satcfdi-decision.md): decisión base sobre producto vs motor
- [docs/roadmap/cfdi-engine-migration/index.md](docs/roadmap/cfdi-engine-migration/index.md): plan de migración del motor CFDI
- [docs/ai/workflow.md](docs/ai/workflow.md): separación entre exploration, implementation y hotfix

## Estado actual

La dirección vigente del repo es preservar `cfdi_inspector` como frontend de producto y mover el análisis principal hacia una API Python respaldada por `python-satcfdi`, con fallback backend a `current-ts` y con retiro gradual del fallback local visible.

## Contribución

Antes de tocar código:

1. Lee [AGENTS.md](AGENTS.md).
2. Si el trabajo es de IA, clasifica la tarea usando [docs/ai/workflow.md](docs/ai/workflow.md).
3. Si el cambio toca el motor CFDI, revisa primero [docs/roadmap/cfdi-engine-migration/index.md](docs/roadmap/cfdi-engine-migration/index.md).
4. Mantén separadas exploración y ejecución.
5. Actualiza la documentación relevante cuando cambie un contrato, decisión o flujo visible.

## Licencia

Estado de licencia por formalizar a nivel de repositorio. Parte del código fuente ya declara `SPDX-License-Identifier: Apache-2.0`, pero falta consolidarlo en un archivo `LICENSE` si se va a distribuir externamente.
