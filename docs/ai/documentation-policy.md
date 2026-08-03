# Documentation Policy

- Status: canonical
- Owner: `docs/ai/`
- Complements: `docs/README.md` and `docs/ai/workflow.md`

## Purpose

This policy governs persistent documentation in this repository. It adapts the
useful principles from an older project without importing that project's file
names, language rules, workflow, or ownership map.

The goal is to preserve trustworthy context while keeping documentation small,
discoverable, and anchored to evidence.

## Scope

This policy applies when creating, moving, splitting, or materially updating:

- repository entry points and contributor guidance;
- architecture, contracts, decisions, roadmaps, security records, or agent
  workflow documentation;
- `PROJECT_STATE.md` checkpoints and pre-existing finding records.

Scratch notes, generated Graphify output, and derived Obsidian notes are not
canonical documentation.

## Authority model

Different questions have different owners. Do not force them into one global
source of truth.

| Question | Authority |
| --- | --- |
| What does the system do now? | Code, tests, deployed behavior, and other primary evidence |
| How must agents operate? | `AGENTS.md` and the policy it routes to |
| Where does documentation belong? | `docs/README.md` |
| What is the stable system structure? | `docs/arquitectura.md` and the relevant contract document |
| Why was a direction selected? | The relevant dated document in `docs/analysis/` |
| What sequence is active for an initiative? | Its `docs/roadmap/**/index.md` and `STATUS.md` |
| What is the current operational checkpoint or a verified pre-existing finding? | `PROJECT_STATE.md` |
| What is known about a security workstream? | Its indexed document under `docs/seguridad/` |
| How should AI-assisted work run? | `docs/ai/` |

Graphify is a derived discovery index. Obsidian is cross-project memory and
synthesis. Neither overrides repository evidence or canonical documents.

## Epistemic classes

Classify material before choosing its destination:

- **Fact:** supported by an exact path, test, diff, commit, log, deployed
  observation, or other primary evidence.
- **Decision:** a selected direction with context, alternatives, and
  consequences.
- **Plan:** intended work that is not yet system behavior.
- **Hypothesis:** an explanation or possibility that still requires validation.
- **History:** a dated record preserved for traceability, not current guidance.
- **Derived insight:** a Graphify or Obsidian connection that must be verified
  against repository sources before promotion.

Do not write a plan or hypothesis as a current fact. Do not erase uncertainty;
label it.

## Document decision workflow

### Gate 0: evidence

Identify the claim and its primary evidence. If evidence is missing, keep the
content in exploration, an open question, or a clearly labelled hypothesis.

### Gate 1: existing owner

Before creating a file:

1. Read `docs/README.md` and the closest thematic index.
2. If `graphify-out/graph.json` exists, run a focused `graphify query` using the
   topic and likely owner names.
3. Confirm candidates in the source files. Graph traversal is discovery, not
   proof.
4. Update an existing owner when its declared responsibility covers the claim.

### Gate 2: split

Create a new canonical document only when at least one material boundary exists:

- a distinct audience or operational owner;
- a different document nature, such as decision versus reference;
- a stable subsystem that would make the current owner hard to navigate;
- repeated reuse that would otherwise duplicate substantive content.

Size alone is a signal, not proof. Temporary uncertainty is not a reason to
create a permanent document.

### Gate 3: discoverability and non-duplication

A new canonical document must:

- declare its purpose, scope, status, and owner or owning area;
- link to evidence rather than copy it when practical;
- be linked from `docs/README.md` or the nearest canonical index;
- state which existing document it complements or replaces;
- avoid becoming a second owner for the same fact.

## Documentation Decision Record

For non-trivial create-versus-update decisions, produce this DDR before editing.
It may remain in the task record unless the decision itself needs durable
history.

```markdown
## Documentation Decision Record

- Topic:
- Epistemic class:
- Primary evidence:
- Candidate owner:
- Graphify preflight query:
- Existing coverage:
- Split boundary, if any:
- Decision: update | create | defer | no documentation change
- Files affected:
- Discoverability update:
- Validation:
```

## Validation and graph refresh

After a persistent documentation change:

1. Inspect the scoped diff and verify paths, links, headings, and factual claims.
2. Confirm that the owner and index still agree.
3. Run `git diff --check`.
4. Run `graphify update .` when the current graph mode supports the update.
5. Repeat the focused query and confirm that it resolves to the intended source.

The repository currently records a Graphify defect in `PROJECT_STATE.md`:
`graphify update .` does not preserve a prior `--code-only` build. If that mode
was used, report the limitation instead of treating the refreshed graph as
equivalent.

## Deterministic automation

The repository applies the accepted decision in
[2026-08-02-zero-cost-documentation-governance.md](../analysis/2026-08-02-zero-cost-documentation-governance.md)
through `scripts/check_documentation_governance.py` and
`docs/ai/documentation-checks.json`.

The automated check is intentionally narrower than this policy. It may block
only on objective repository invariants: missing local document references and
a new canonical document absent from its owner index. Ambiguous placement is
recorded as `requires review`; it is not presented as semantic understanding.
Local findings live under `.git/`, and CI publishes its result only in the run
summary. Neither path may rewrite canonical documentation automatically.

## Obsidian boundary

Do not bulk-export this repository's AST graph into the personal vault. Curated
cross-project notes may be promoted to Obsidian only when they include:

- `authority: derived`;
- repository and source commit;
- exact source paths;
- capture date;
- the condition that makes the note stale.

An Obsidian insight returns to the repository only through a reviewed document
decision backed by current repository evidence. Disposable Graphify exports must
use an isolated namespace, never the root of an existing personal vault.
