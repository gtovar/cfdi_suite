# DECISION UPDATE

TRIGGER:
The original implementation decision assumed that Vitest + file-level `jsdom` would work with the current repo setup and existing dependencies.

OBSERVED DEVIATION:
Running the new component tests failed before test execution because the current environment cannot initialize `jsdom` under Vitest due to an ESM/CJS dependency conflict in `html-encoding-sniffer` and `@exodus/bytes`.

UPDATED DECISION:
Do not keep pushing on `jsdom` in this repo. Switch the minimal component-test convention to a lighter DOM environment that works with Vitest here. The preferred path is `happy-dom` if it can be added cleanly as a dev dependency. Keep the rest of the scope unchanged:
- local component test convention
- toolbar coverage
- findings sidebar coverage

WHY THIS IS STILL WITHIN THE SLICE:
The goal of the slice is minimum viable UI validation, not `jsdom` specifically. Changing the DOM environment is a correction to the testing decision, not a scope expansion.
