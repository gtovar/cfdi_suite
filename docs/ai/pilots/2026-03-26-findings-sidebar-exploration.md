# EXPLORATION

PROBLEM:
The findings sidebar only renders the first four findings and gives no signal when more findings exist. That hides analysis output and can mislead the user into reading an incomplete picture of the XML.

OPTIONS:
A: Keep showing only four findings with no additional UI.
B: Keep the compact default view, but show a hidden-count summary and a toggle to reveal or collapse the full list.
C: Always render all findings.

RISKS:
A: Lowest implementation cost, but preserves the hidden-information problem.
B: Adds one local interaction, but keeps the sidebar compact while making the truncation explicit and reversible.
C: Removes ambiguity, but can make the sidebar much heavier for dense documents.

PROPOSED DECISION:
Choose option B. The sidebar should default to four findings, show how many are hidden, and provide a local toggle to expand or collapse the full list. Do not change finding ranking, severity styling, or the rest of the summary panel.

OPEN QUESTIONS:
No blocking questions. The toggle should stay local to the sidebar and should reset naturally when the component remounts for a new document.
