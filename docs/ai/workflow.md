# AI Workflow

This repo uses three task types:

## Exploration

Goal: reduce ambiguity and produce a decision.

Allowed outputs:
- options
- risks
- recommendation
- discardable spikes marked `[SPIKE] - no shipping`

Rules:
- ambiguity is allowed at the start
- spikes must not touch production code
- exploration does not ship code or commits
- if exploration exceeds 30 minutes, split the problem or close a partial decision

## Implementation

Goal: execute a prior decision.

Required input:
- explicit closed decision

Expected output:
- code
- tests or validation updates
- verifiable change

Rules:
- do not expand scope
- do not invent features
- do not refactor outside the stated slice

## Hotfix

Goal: restore correct behavior quickly with a compressed decision step.

Rules:
- a hotfix still requires an explicit fix hypothesis
- keep the scope minimal and incident-focused
- validate the fix immediately after implementation

## Decision Gate

A task is ready for implementation only when:

- inputs and outputs are defined
- contracts are defined
- scope is defined
- constraints are defined
- alternatives were considered
- known risks are stated
- definition of done is stated
- two independent implementers would likely produce equivalent results

If any of those are missing, the task remains in exploration.

## Flow Separation

Exploration and implementation must not happen in the same task flow.

If exploration produces a decision and work should continue, start a new implementation task using that decision as input.

## Deviations

When implementation returns something different from the decision:

- if it matches the decision, continue
- if it deviates and seems better, return to exploration and update the decision first
- if it deviates and is worse, return to exploration and correct the decision first

Never correct implementation without correcting the decision first.
