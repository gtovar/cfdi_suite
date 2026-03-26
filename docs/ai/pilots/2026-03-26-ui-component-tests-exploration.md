# EXPLORATION

PROBLEM:
Two completed pilots exposed the same weakness: the process controls scope well, but UI validation still relies on build output and manual reasoning. The repo has Vitest, but no current convention for testing React component rendering or local interactions.

OPTIONS:
A: Keep relying on `npm test` and `npm run build` without component-level UI coverage.
B: Add a minimal component-test pattern based on Vitest + jsdom + React DOM utilities, and apply it to the toolbar and findings sidebar.
C: Introduce a fuller UI testing stack and broader conventions now.

RISKS:
A: Lowest setup cost, but preserves the exact blind spot already identified twice.
B: Adds a small local testing pattern and a couple of focused tests without changing the wider tooling footprint.
C: Likely over-scoped for the current need and would turn a focused validation slice into a testing initiative.

PROPOSED DECISION:
Choose option B. Define a minimal component test pattern using file-level jsdom environment, a tiny local render helper, and DOM assertions through Vitest. Apply it to the extract toolbar and findings sidebar only, covering the behaviors already identified as weakly validated.

OPEN QUESTIONS:
No blocking questions. The convention should stay small and local; it does not need snapshot testing, browser automation, or new third-party dependencies.
