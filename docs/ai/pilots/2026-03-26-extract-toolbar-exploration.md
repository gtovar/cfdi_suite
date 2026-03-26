# EXPLORATION

PROBLEM:
The extract workspace toolbar exposes search, sorting, column filters, and selection state, but it does not show the impact of the top-level search on the dataset in the same interaction zone. The only filtered row count appears in pagination, which forces the user to scan away from the active controls to understand whether the search did anything.

OPTIONS:
A: Keep the current toolbar and rely on pagination for record counts.
B: Add compact status chips to the toolbar that summarize search scope, filtered row count versus total rows, active column filters, and selected rows.
C: Add a separate summary banner between the toolbar and the table.

RISKS:
A: Lowest implementation cost, but preserves the current feedback gap and does not validate the new workflow with a meaningful UI change.
B: Slightly denser toolbar, but keeps context next to the controls and stays within the existing visual language.
C: Clear feedback, but introduces another UI band and increases visual weight for a small state summary.

PROPOSED DECISION:
Choose option B. Extend the extract grid controller with the total row count and show compact status chips inside the toolbar for search scope, filtered rows versus total rows, active column filters, and selected rows. Do not introduce new filtering behavior, new controls, or changes to pagination.

OPEN QUESTIONS:
No open questions block implementation. The summary chips should remain read-only and should reuse current state instead of adding new derived sources of truth.
