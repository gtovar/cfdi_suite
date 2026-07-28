# 07 — Auth fail-closed en producción

## Evidencia original

**Hecho verificado:** `verify_user_identity` devuelve `dev-tenant` cuando falta
`API_BEARER_TOKEN`. Es útil localmente pero, si el secreto falta en despliegue,
abre la API. El despliegue no fuerza aún una bandera de producción fail-closed.

## Análisis decision-expander

1. **Qué existe realmente / contexto omitido:** B-lite depende de secreto de
   entorno y el health/internal tienen excepciones explícitas.
2. **Qué parece que se quiere decir / restricciones reales:** producción debe
   fallar al arrancar sin secreto; desarrollo local queda posible sólo por una
   decisión de configuración explícita.
3. **Qué podría estar mal nombrado / supuestos no verificados:** “sin token es
   desarrollo” no identifica el entorno ni prueba intención del operador.
4. **Capacidades nativas ya existentes:** lifecycle FastAPI y variables de
   Cloud Run permiten validar temprano; Secret Manager inyecta el secreto.
5. **Capacidades con configuración o composición:** `REQUIRE_API_AUTH=true` en
   deploy más guardia de lifespan transforma omisión en fallo visible.
6. **Límites reales:** no reemplaza rotación, login ni tenant isolation; sólo
   evita fail-open por configuración faltante.
7. **Alternativas no obvias:** detectar `ENV=production`; es más implícito y
   frágil que una bandera afirmativa desplegada junto al secreto.
8. **Riesgos / costo de no explorar:** secreto ausente publica API; activar
   bandera sin secret deja revisión sin instancia saludable, que es preferible
   al acceso anónimo pero exige orden de deploy.
9. **Costo de sobreestimar / prueba mínima:** comprobar que el secreto llega al
   runtime, no sólo existe en Secret Manager; probar arranque con/sin ambos.
10. **Recomendación:** proceder como garantía de despliegue con flag explícito.

## Cierre (2026-07-28)

**CERRADO por Decision Expander.** El workflow inyecta
`API_BEARER_TOKEN` desde Secret Manager y ahora fija
`REQUIRE_API_AUTH=true`. El lifespan aborta antes de atender tráfico si la
bandera está activa y falta el secreto; sin bandera, desarrollo local conserva
su modo explícito sin secreto.

Evidencia: `backend/.venv/bin/python -m pytest
backend/tests/test_lifespan_api_auth.py -q` pasó **3 pruebas**: producción sin
secreto falla, producción con secreto arranca y local sin bandera arranca.

Pendiente operativo, fuera de este cambio: en el siguiente deploy confirmar
que la revisión nueva recibe el secreto y queda Ready antes de mover tráfico.

## Implementación

Añadir `REQUIRE_API_AUTH=true` al deploy Cloud Run y abortar lifespan si está
activa sin `API_BEARER_TOKEN`; desarrollo sin bandera sigue explícito.

## Pruebas

Arranque producción sin secreto falla; producción con secreto y local sin bandera
arrancan; verificar la configuración de deploy.

## Rollback

Retirar la bandera y revertir guardia sólo como respuesta operativa temporal;
corregir primero la inyección de Secret Manager.
