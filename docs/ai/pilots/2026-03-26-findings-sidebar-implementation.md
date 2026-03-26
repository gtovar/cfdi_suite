# IMPLEMENTATION

OBJECTIVE:
Make finding truncation explicit and user-controllable without changing the existing severity presentation or the summary section.

DECISION:
Render the first four findings by default, show the count of hidden findings when applicable, and add a toggle to switch between compact and full list modes.

SCOPE:
Includes:
- local sidebar state for expanded or collapsed mode
- hidden finding count messaging
- toggle control for showing all or fewer findings

Excludes:
- changes to finding sort order
- changes to finding styling or severity logic
- pagination or search inside findings

FOCUS FILES:
- src/components/FindingsSidebar.tsx

CONSTRAINTS:
- keep the current visual language
- preserve the compact default view
- do not alter the source finding list

VALIDATION:
- automated checks: npm test and npm run build
- review deviation: confirm the compact default still shows four findings and the expanded state only reveals additional existing findings
