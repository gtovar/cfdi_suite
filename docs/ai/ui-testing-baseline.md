# UI Testing Baseline

This repo now has a minimal baseline for local component UI tests.

## Current Baseline

- DOM environment: `happy-dom`
- Local render helper: `src/test/renderReact.tsx`
- Current coverage examples:
  - `src/components/extract-workspace/ExtractWorkspaceToolbar.test.tsx`
  - `src/components/FindingsSidebar.test.tsx`

## Recommended Use

Use this baseline for:
- components with meaningful local state
- components where rendering output is part of the behavior
- focused checks on local interactions already covered by a product slice

## Out of Scope

This baseline does not provide:
- browser automation
- snapshot testing
- layout validation
- style assertions
- broad repo-wide coverage conventions

## Rule

Treat this as the minimum viable UI validation layer for targeted slices.
Do not expand it unless a product task clearly requires more.
