# EXPLORATION

PROBLEM:
The app computes impacted concepts and already mounts `ConceptDetailModal`, but there is no visible path in the current UI to open concept detail. This leaves a useful product capability disconnected and forces users to infer issues without a direct drill-down.

OPTIONS:
A: Leave the modal disconnected and treat it as future work.
B: Add a compact list of impacted concepts in the findings sidebar that opens the existing detail modal.
C: Add concept-detail entry points inside the extract workspace table.

RISKS:
A: Lowest effort, but preserves a dead-end in the current product.
B: Reuses an existing analysis area and keeps the drill-down close to findings, with limited implementation scope.
C: Potentially useful, but couples the feature to table state and introduces more surface area than needed for the first connection.

PROPOSED DECISION:
Choose option B. Show a compact impacted-concepts section in the findings sidebar and use it to open the existing `ConceptDetailModal`. Limit the list to a small default set with a simple count summary when more concepts are impacted. Do not redesign the modal or the extract workspace.

OPEN QUESTIONS:
No blocking questions. The sidebar should use the canonical impacted concepts already computed in `cfdi`.
