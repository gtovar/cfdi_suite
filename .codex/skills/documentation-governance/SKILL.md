---
name: documentation-governance
description: Decide whether to update, create, move, split, or defer persistent repository documentation using evidence, existing ownership, Graphify-assisted discovery, and a Documentation Decision Record. Use for canonical Markdown changes, architecture or contract docs, decision records, roadmaps, project-state updates, documentation reorganizations, and requests to prevent duplicate or orphaned docs.
---

# Documentation Governance

## Source of truth

Read `docs/ai/documentation-policy.md` completely before acting. Treat it as the
canonical policy. Do not duplicate its rules in this skill or infer ownership
from inherited documentation outside this repository.

## Workflow

1. Classify the proposed content as fact, decision, plan, hypothesis, history,
   or derived insight.
2. Identify exact primary evidence. If a factual claim lacks evidence, defer it
   or label it as a hypothesis.
3. Read `docs/README.md` and the nearest thematic index.
4. If `graphify-out/graph.json` exists, run a focused `graphify query` for the
   topic and candidate owners. Verify every useful result in its source file.
5. Produce the Documentation Decision Record from
   `docs/ai/templates/documentation-decision.md` for a non-trivial decision.
6. Prefer the existing owner. Create or split only when the policy's boundary
   gate is satisfied.
7. Make the scoped change and update the nearest canonical index when needed.
8. Validate the diff, links, paths, evidence, and ownership. Run
   `git diff --check`.
9. Run `graphify update .` when compatible with the graph's build mode, then
   repeat the preflight query to confirm discoverability. Surface the recorded
   `--code-only` update limitation when applicable.

## Boundaries

- Repository evidence and canonical documents always outrank Graphify or
  Obsidian derivatives.
- Do not create new Email Cleaner-era paths merely because an inherited rule
  names them.
- Do not require English globally; follow the language and audience of the
  local owner document.
- Do not add hooks, CI gates, or a plugin unless a separately approved decision
  defines an objective invariant and its failure behavior.
- Do not bulk-export the AST graph into an existing personal Obsidian vault.
  Promote only curated notes with repository, commit, sources, date, staleness,
  and `authority: derived`.
