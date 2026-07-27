# 07 — Plan de Respuesta a Incidentes

> **Si algo se rompe a las 2am, este doc te dice que hacer.**
> Practico. Sin teoria. Acciones concretas.

---

## Clasificacion de Incidentes

### Sev 1 — Critico (respuesta inmediata)

- Produccion caida: Cloud Run no responde, Vercel error 500
- Filtracion de datos: XMLs/PDFs de otras sesiones accesibles
- Compromiso de secretos: `REDIS_PASSWORD`, `GCP_SA_KEY`, `PUSHER_SECRET`, `VERCEL_TOKEN` expuestos
- Abuso masivo: 1000+ requests/min usando creditos Diverza

**SLA:** 15 min (notificar), 1h (contain), 4h (restore)

### Sev 2 — Alto (respuesta en horas)

- Degradacion parcial: Redis caido (Pusher events no funcionan, analisis sigue)
- Actividad sospechosa: intentos de acceso a `/api/internal/*` sin OIDC
- Error rate spike: 10%+ errores en Sentry en 10 min
- Dependencia externa caida: Diverza API down, Pusher down

**SLA:** 1h (notificar), 8h (contain/resolve)

### Sev 3 — Bajo (proximo business day)

- Warning en CI: react-doctor finding nuevo, bandit LOW, npm audit MODERATE
- Dependabot PR: actualizacion de dependencia menor
- Certificado por vencer: dominio Vercel, certificado Upstash

---

## Deteccion

### Automatica (existe)

| Senal | Herramienta | Umbral |
|-------|-------------|--------|
| Errores backend | Sentry (`main.py:51`) | 5+ eventos/min o error rate >10% |
| Errores frontend | Sentry (`main.tsx:14`) | 5+ eventos/min |
| Cloud Run errores 5xx | GCP Monitoring | > 10/min |
| Cloud Run latencia | GCP Monitoring | P99 > 30s |
| Cloud Tasks failures | GCP Monitoring | Failure rate > 5% |

### A implementar hoy

| Senal | Como | Esfuerzo |
|-------|-----|----------|
| Redis failures | Sentry alert en `safe_redis_call` > 10 errores/min | 15 min |
| Diverza credit exhaustion | Contador en Redis + alerta | 2h |
| Pusher connection errors | Contador de eventos fallidos | 1h |
| `/api/internal/*` access without OIDC | Sentry alert en cada 403 | Ya en recos `03-backend.md` |

---

## Response Checklist — Sev 1

### DETECT (t=0)

```
□ Recibir alerta
□ Verificar en Sentry: spike real o ruido?
□ Verificar GCP Cloud Run logs: que endpoint falla?
□ Determinar blast radius: afecta a todos o solo feature?
```

### CONTAIN (t+15min)

```
□ Fuga de secretos:
  □ Rotar REDIS_PASSWORD en Upstash
  □ Rotar PUSHER_SECRET en Pusher
  □ Desactivar GCP_SA_KEY en IAM
  □ Invalidar VERCEL_TOKEN
  □ Actualizar GitHub Secrets con nuevos valores
  □ Redeploy (push a main)

□ Abuso masivo:
  □ Matar servicio: gcloud run services update cfdi-suite-api --max-instances=0 --region=us-central1
  □ O reducir: --concurrency=1

□ Filtracion de datos:
  □ Matar servicio (paso arriba)
  □ Revocar signed URLs (eliminar SA key temporal)
```

### ERADICATE (t+1h)

```
□ Root cause: git log, deploy log, GCP logs
□ Fix: PR de hotfix → deploy inmediato
□ Verificar post-fix: health endpoint, Pusher, Redis, Diverza
```

### RECOVER (t+4h max)

```
□ Restaurar max-instances=10
□ Verificar batches activos no perdidos
□ Verificar Cloud Tasks zombies
□ Monitor 30 min: Sentry 0 errores, Pusher events flowing
```

### POST-MORTEM (t+48h)

```markdown
## Post-Mortem: [TITULO]

**Fecha:** [ ]
**Duracion:** [ ] min (deteccion → recovery)
**Severidad:** Sev 1 / Sev 2

### Timeline
- [HH:MM] — [Evento]
- [HH:MM] — [Deteccion]
- [HH:MM] — [Contencion]
- [HH:MM] — [Fix deployado]
- [HH:MM] — [Recovery completo]

### Que paso
[2-3 frases causa raiz]

### 5 Whys
1. Por que? → 2. → 3. → 4. → 5. [root cause]

### Que salio bien
- [ ]

### Que salio mal
- [ ]

### Action items
- [ ] [Accion] — Owner: [ ] — Due: [ ]
```

---

## Sev 2 — ALTO

Mismo proceso que Sev 1 con timebox extendido. Kill switch solo si necesario.

---

## Contactos (Roles, no Nombres)

| Recurso | Quien tiene acceso | Puede |
|---------|-------------------|-------|
| GitHub repo | Owner + collaborators | Merge PRs, ver secrets, trigger deploys |
| GCP console | Owner (`GCP_SA_KEY` holder) | Deploy, kill services, rotar SA keys, ver logs |
| Upstash | Owner (account email) | Rotar Redis password |
| Pusher | Owner (account email) | Rotar secret, disable client events |
| Vercel | Owner (`VERCEL_TOKEN` holder) | Rollback, deploy |
| Sentry | Owner + org members | Ver errores, config alertas |

---

## Rollback Procedures

### Cloud Run

```bash
# Listar revisiones
gcloud run revisions list --service=cfdi-suite-api --region=us-central1

# Rollback a revision buena
gcloud run services update-traffic cfdi-suite-api \
  --region=us-central1 \
  --to-revisions=REV_BUENA=100
```

### Vercel

```bash
vercel rollback  # Instantaneo via CLI
# O: Dashboard → Deployments → Promote to Production
```

### Redis Flush

```bash
redis-cli -h $REDIS_HOST -p $REDIS_PORT -a $REDIS_PASSWORD --tls FLUSHALL
# Precaución: borra TODOS los estados de batch activos
```

---

## Comunicacion

### Interna (Slack/Discord)

```
🚨 INCIDENT: Sev [1/2] — [Titulo]
Status: [Investigando / Contenido / Resuelto]
Impacto: [que no funciona]
Blast radius: [datos expuestos si aplica]
```

### Usuarios (si aplica)

```
El servicio experimento [problema] entre [hora] y [hora].
Ya esta restaurado. [Que paso, que hicimos].
```

### Regulatoria (LFPDPPP — Mexico)

Si hay filtracion de RFCs:
1. Notificar al INAI dentro de 72 horas
2. Notificar a titulares afectados
3. Documentar: que datos, cuantos titulares, acciones tomadas

---

## Drill Anual

**Frecuencia:** 1 vez/ano (proximo: Julio 2027)
**Escenario:** `REDIS_PASSWORD` filtrado en commit publico → ejecutar checklist Sev 1 completo → medir tiempo real vs SLA

---

> La diferencia entre un incidente malo y uno catastrofico = tener este doc a mano, no googlear comandos de gcloud a las 2am.
