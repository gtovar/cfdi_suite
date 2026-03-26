# IMPLEMENTATION

OBJECTIVE:
Reconnect concept drill-down to the visible product flow by letting users open concept detail from the findings sidebar.

DECISION:
Render a compact impacted-concepts list in the sidebar and wire each item to the existing `ConceptDetailModal`.

SCOPE:
Includes:
- deriving impacted concept objects from `cfdi.impactedConceptIndexes`
- passing impacted concepts and a selection callback into the sidebar
- rendering a compact impacted-concepts section with buttons
- opening the existing modal when a concept is selected

Excludes:
- changes to modal structure
- extract table integration
- new sorting or filtering for concepts

FOCUS FILES:
- src/App.tsx
- src/components/FindingsSidebar.tsx
- src/components/FindingsSidebar.impactedConcepts.test.tsx
- src/App.test.tsx

CONSTRAINTS:
- keep the sidebar compact
- reuse existing modal state
- avoid introducing duplicate concept sources of truth

VALIDATION:
- npm test
- npm run build
- review deviation against the chosen sidebar-driven drill-down flow
