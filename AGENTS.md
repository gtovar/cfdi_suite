## Wiki Knowledge Base
Path: /Users/gil/Documents/claude-obsidian

When you need context not already in this project:
1. Read wiki/hot.md first (recent context cache)
2. If not enough, read wiki/index.md
3. If you need domain details, read the relevant domain sub-index
4. Only then drill into specific wiki pages

Do NOT read the wiki for general coding questions or tasks unrelated to [domain].

## Documentation governance

For any persistent documentation creation, move, split, or material rewrite,
use the repo-local `documentation-governance` skill and follow
`docs/ai/documentation-policy.md`. Keep `AGENTS.md` as a short router; the policy
owns the detailed rules. Repository evidence and canonical documents outrank
Graphify and Obsidian derivatives. Before creating a document, use the existing
documentation map plus a focused Graphify query; after a documentation change,
refresh the graph when its build mode supports `graphify update .`.
At session re-entry, run
`python3 scripts/check_documentation_governance.py --show-pending` and review any
persisted findings before making a documentation decision.
During an active task, infer whether a requested or encountered change creates
or alters a durable product, architecture, contract, or workflow decision even
when the user does not call it a decision. If the Decision Gate in
`docs/ai/workflow.md` is not satisfied, route the work to exploration instead
of silently choosing material tradeoffs.

## Política de hallazgos preexistentes

Si durante una tarea encuentras algo roto que NO es de tu cambio (test que ya
fallaba, error de lint previo, warning de react-doctor viejo):

1. **Prohibido descartarlo en silencio.** Decir "es preexistente" sin dejar
   rastro escrito no es aceptable.
2. Anótalo en `PROJECT_STATE.md §Hallazgos preexistentes` con evidencia
   verificable de que es preexistente (p. ej. `git stash` y reproducir el
   fallo sin tus cambios).
3. Si el hallazgo es de react-doctor, regístralo/referéncialo además en
   `docs/react-doctor-veredictos.md` (la fuente de verdad de esos veredictos).
4. No lo arregles dentro de tu tarea salvo que el usuario lo pida — anotarlo
   es obligatorio, arreglarlo es decisión aparte.

Para verificar si un hallazgo de react-doctor es tuyo o preexistente:
`npx react-doctor --scope changed` (desde `frontend/`) reporta solo lo
introducido contra la rama base.

## Política de código aparentemente sin uso

**Nunca borres código "muerto" (archivos, exports, dependencias, métodos sin
referencias) sin investigación de propósito Y confirmación explícita del
usuario.** Ya ocurrió que código "sin uso" a punto de borrarse resultó ser
exactamente lo que una feature posterior necesitaba. Flujo obligatorio:
investigar (`git log`, imports históricos, features en desarrollo, imports
dinámicos/workers) → clasificar con evidencia → proponer al usuario → borrar
solo con su confirmación. Detalle en `docs/react-doctor-veredictos.md`
§Política de código no usado.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
