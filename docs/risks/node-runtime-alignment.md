# Risk: Node Runtime Alignment

## Status

Open

## Trigger

Adding `happy-dom` for local component UI tests surfaced engine warnings during install.

## Observed Signal

The current local runtime is Node 18, while multiple current dependencies prefer Node 20+.

Examples surfaced during install:
- `happy-dom`
- `vitest`
- `jsdom`
- `@vitejs/plugin-react`
- `@google/genai`

## Risk

The repo currently works, but runtime drift can turn future dependency updates or tooling changes into avoidable breakage.

## Current Impact

- `npm test` passes
- `npm run build` passes
- install-time engine warnings now indicate a real alignment gap

## Next Decision

Handle runtime alignment as a separate technical decision from the AI workflow and UI testing slices.

## Suggested Next Step

Decide whether this repo should stay on Node 18 temporarily with known risk, or move to a Node 20+ baseline and update local/project guidance accordingly.
