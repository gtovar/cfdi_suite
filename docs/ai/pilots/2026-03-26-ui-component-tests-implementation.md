# IMPLEMENTATION

OBJECTIVE:
Add a minimal, reusable component-testing convention for critical UI state rendering and local interactions.

DECISION:
Use Vitest with file-level `jsdom`, a small local React render helper, and focused DOM assertions. Cover:
- extract toolbar state summary rendering
- findings sidebar compact/expanded behavior and reset on CFDI change

SCOPE:
Includes:
- local test helper for rendering React components into jsdom
- one test file for `ExtractWorkspaceToolbar`
- one test file for `FindingsSidebar`

Excludes:
- browser automation
- snapshot testing
- global testing framework changes
- broader component test rollout

FOCUS FILES:
- src/test/renderReact.tsx
- src/components/extract-workspace/ExtractWorkspaceToolbar.test.tsx
- src/components/FindingsSidebar.test.tsx

CONSTRAINTS:
- do not add new external dependencies
- keep the convention lightweight and local
- assert behavior that matters to current pilots instead of testing styling exhaustively

VALIDATION:
- npm test
- npm run build
- review deviation against the chosen convention and covered behaviors
