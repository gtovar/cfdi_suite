# IMPLEMENTATION

OBJECTIVE:
Add immediate dataset feedback to the extract workspace toolbar so users can see what the top-level search and current grid state are doing without having to look down at pagination.

DECISION:
Use compact read-only status chips in the existing toolbar to show:
- search scope
- filtered rows versus total rows
- active column filter count
- selected row count

SCOPE:
Includes:
- extending the extract grid controller with the total row count needed for the summary
- rendering the new summary chips in the toolbar
- keeping the existing controls and pagination behavior unchanged

Excludes:
- new filters
- new sorting behavior
- changes to table or pagination logic
- persistence changes

FOCUS FILES:
- src/app/hooks/useExtractGridState.ts
- src/components/extract-workspace/types.ts
- src/components/extract-workspace/ExtractWorkspaceToolbar.tsx

CONSTRAINTS:
- stay within the current visual system
- do not expand scope beyond toolbar state visibility
- use existing grid state as the source of truth

VALIDATION:
- automated checks: npm test and npm run build
- review deviation: compare the final UI state summary against the decision and confirm no new behavior was introduced
