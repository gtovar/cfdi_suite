# Registro de Arquitectura: Optimización Masiva, Redis y Observabilidad

**Fecha:** 8 de Julio de 2026
**Objetivo:** Adaptar la arquitectura de `cfdi_suite` para procesar de miles a decenas de miles de facturas simultáneas (archivos pesados de hasta 6MB) sin saturar los límites de memoria de Redis en Upstash y permitir el diagnóstico preciso de cuellos de botella mediante observabilidad (Cloud Trace).

## 1. El Problema del "Tanque Lleno" (Memoria en Redis)
En el módulo de generación de PDFs (`pdf.py`), el flujo consistía en subir archivos XML, guardarlos temporalmente en Redis, y una vez que Cloud Tasks generaba el PDF, almacenar el binario pesado resultante de vuelta en Redis para su posterior descarga agrupada (en ZIP).

* **El Límite:** El plan gratuito de Upstash Redis tiene un límite estricto de 256 MB. Al procesar XMLs (especialmente los de proveedores como Miniso que pueden pesar >5 MB por factura), el almacenamiento de Redis (el "tanque") se desbordaba al procesar lotes medianos, causando errores de *Out of Memory*.

### La Solución Implementada (Opción A: zlib)
Dado que los archivos XML y PDF contienen texto y estructuras altamente repetitivas, se implementó compresión en tiempo real utilizando la librería nativa de Python `zlib`.
* **Archivos Afectados:** `backend/app/routers/pdf.py`
* **Cambio:** Se aplicó `zlib.compress()` antes de inyectar datos a Redis (`pdf:xml:{job_id}` y `pdf:data:{job_id}`) y `zlib.decompress()` inmediatamente al extraerlos de la caché.
* **Resultado:** Se redujo el tamaño de los datos en memoria en más de un 75%, cuadruplicando la capacidad del sistema y permitiendo procesar lotes de ~4,000 facturas simultáneas totalmente gratis, elevando drásticamente el techo sin cambiar de infraestructura.

*(Nota: `batch.py` no requirió esta optimización porque únicamente guarda JSONs diminutos con el estatus y delega el XML directamente a Cloud Tasks sin tocar la RAM de Redis prolongadamente).*

## 2. Limpieza de Código Legado (El fantasma de ARQ)
Durante el análisis, se observó en los logs el mensaje de error: `"ARQ: Redis no disponible — canvas_pipeline corre en modo sync"`.
* **El Problema:** La librería `ARQ` estaba intentando conectar a Redis en el arranque de la app, pero fallaba silenciosamente porque le faltaba la contraseña y configuración SSL de Upstash.
* **El Descubrimiento:** Al revisar la arquitectura de `task_dispatcher.py`, descubrimos que el sistema *ya no utiliza ARQ*. Toda la delegación asíncrona ("La Válvula Reguladora") la ejecuta impecablemente **Google Cloud Tasks**.
* **La Solución Implementada:** Se eliminó por completo el bloque de inicialización de ARQ en `backend/app/main.py` para limpiar la base de código ("código zombie"), reducir los tiempos de arranque y eliminar confusiones futuras.

## 3. Límites de Infraestructura de Red (Vercel vs Cloud Run)
Durante las pruebas de estrés con archivos ZIP pesados (39 MB y 26 MB), nos topamos con errores **413 Request Entity Too Large**.
* **Límite de Vercel:** Las Serverless Functions limitan el payload entrante a **4.5 MB**.
* **Límite de Cloud Run:** Rechaza de tajo peticiones mayores a **32 MB**.
* **La Solución Actual:** Se generó un ZIP "micro" de 3.3 MB para probar y confirmar exitosamente el flujo completo por debajo del radar de Vercel.
* **La Solución Arquitectónica Futura (Opción B):** Si el negocio requiere procesar lotes de >50 MB en una sola petición, se deberá migrar a un modelo de **Signed URLs**. El frontend deberá subir el ZIP directamente a un bucket de Google Cloud Storage, y Cloud Run simplemente lo leerá desde el disco interno, esquivando por completo las restricciones HTTP.

## 4. Observabilidad y Diagnóstico Quirúrgico (Cloud Trace)
Para escalar un sistema a 30,000 facturas, es vital dejar de adivinar dónde están los cuellos de botella (usando la analogía: ¿es el tubo, la válvula, la bomba o la regadera la que falla?).

* **La Solución Implementada:** Se instalaron e integraron los sensores de **Google Cloud Trace** mediante OpenTelemetry.
* **Cambios realizados:**
  1. Se agregaron las librerías a `requirements.txt`: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-exporter-gcp-trace`.
  2. En `main.py` se instrumentó de forma global todo el tráfico entrante de FastAPI.
  3. En `pdf.py`, se envolvió específicamente la función pesada (`generate()`) en un span manual llamado `"generacion_pdf_intensiva"`.

### ¿Cómo interpretar los resultados?
A partir de ahora, todo el tráfico masivo de Cloud Tasks quedará documentado en la consola de Google Cloud (Sección: **Trace**).
Cualquier desarrollador futuro podrá ver una gráfica de cascada (Waterfall) para identificar exactamente cuántos milisegundos pasó una petición en Redis vs la conversión del PDF. Esto permite invertir tiempo de optimización *únicamente* donde realmente aporta valor y escala al sistema.
