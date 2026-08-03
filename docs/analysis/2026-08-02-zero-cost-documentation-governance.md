# Decisión: gobernanza documental determinista y sin costo de API

- Fecha: 2026-08-02
- Estado: aceptada e implementada
- Owner: `docs/ai/`
- Complementa: [política de documentación](../ai/documentation-policy.md)

## Contexto

El repositorio necesita conservar hallazgos documentales entre sesiones y
revisar los mismos invariantes tanto en el equipo local como en GitHub. No se
autoriza comprar créditos de modelos ni minutos adicionales de automatización,
y un proceso autónomo no puede prometer comprensión semántica sin un modelo en
ejecución.

La evidencia primaria previa a esta decisión fue:

- GitHub Actions ya ejecutaba controles por `push` y `pull_request` bajo
  `.github/workflows/`;
- el repositorio ya tenía un `pre-commit` local y un evento de inicio de sesión
  en `.claude/settings.json`;
- `docs/ai/documentation-policy.md` ya separaba evidencia, ownership y revisión
  humana;
- no había un verificador documental compartido por Git y CI.

## Decisión

Se adopta un lazo híbrido, local y orientado a eventos:

1. `scripts/check_documentation_governance.py` inspecciona sólo documentos
   modificados y los índices que los poseen.
2. El `pre-commit` local ejecuta el verificador sobre el índice de Git.
3. `.github/workflows/documentation-governance.yml` ejecuta el mismo programa
   en cada `push` y pull request, sin calendario periódico.
4. Los hallazgos locales se conservan en
   `.git/documentation-governance/pending.json`.
5. Al reingresar, Codex consulta y muestra la cola mediante la instrucción
   versionada en `AGENTS.md`.
6. La interpretación y la decisión de documentación siguen pasando por la
   política y por una sesión activa de Codex.

El verificador usa únicamente la biblioteca estándar de Python, Git y archivos
del repositorio. No instala dependencias, no requiere secretos y no realiza
llamadas de red.

## Invariantes y comportamiento de fallo

Los siguientes invariantes son objetivos y bloquean el hook o CI con código 1:

- todo enlace Markdown local de un documento examinado debe resolver en el
  mismo snapshot de Git;
- toda ruta documental explícita escrita entre backticks debe existir;
- todo documento canónico nuevo debe ser descubrible desde su índice
  propietario o desde un enlace al directorio que lo contiene.

Los casos que no admiten una decisión puramente mecánica se registran como
`requiere revisión` y terminan con código 0. El caso inicial es un documento
modificado fuera de una ubicación canónica reconocida. Una falla al cargar la
configuración o consultar Git termina con código 2 porque el control no llegó a
ejecutarse de forma confiable.

La configuración declarativa vive en
`docs/ai/documentation-checks.json`. Los documentos bajo `docs/` usan el
`README.md` o `index.md` más cercano como propietario; los tres documentos
canónicos de raíz se reconocen explícitamente. Los artefactos derivados o
vendorizados de agentes y Graphify quedan fuera del control.

## Alternativas descartadas

- Auditoría semántica desatendida: no es viable con presupuesto cero y
  presentaría heurísticas como comprensión.
- Ejecuciones programadas: consumen minutos sin actividad nueva y no aportan
  evidencia distinta a la de los eventos Git.
- Reescritura automática de documentos: mezcla detección con decisión y puede
  crear una segunda fuente de verdad.
- Dependencia exclusiva del hook local: `--no-verify` puede omitirlo; el evento
  remoto conserva la segunda línea de defensa.

## Consecuencias y límites

- La inactividad no genera ejecuciones ni errores.
- Un hook omitido se compensa en el siguiente `push`, mientras GitHub Actions
  siga disponible dentro de los minutos incluidos.
- Si esos minutos dejan de estar incluidos, el control local continúa
  funcionando.
- Los hallazgos de CI quedan en el resumen de la ejecución; no se descargan ni
  escriben automáticamente en el repositorio.
- La existencia de una ruta no prueba que una afirmación compleja sea correcta.
  Esa revisión corresponde a Codex durante una sesión activa.

## Validación operativa

```bash
python3 -m unittest tests.test_documentation_governance -v
python3 scripts/check_documentation_governance.py --staged
python3 scripts/check_documentation_governance.py --show-pending
python3 scripts/check_documentation_governance.py --install-hook
```
