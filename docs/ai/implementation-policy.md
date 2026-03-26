# AI Implementation Policy

This policy separates decision-making from execution.

## ChatGPT Use

Use ChatGPT for:
- framing the problem
- comparing options
- identifying risks
- proposing a decision
- reviewing whether implementation matches the decision

ChatGPT should not:
- treat open-ended exploration as implicit approval to ship code
- rewrite the implementation goal mid-flight without creating a new decision

## Codex Use

Use Codex for:
- implementing a closed decision
- updating the relevant code paths
- adding or updating tests when needed
- reporting any deviation from the requested decision

Codex should not:
- implement without a prior decision on implementation tasks
- expand scope beyond the stated slice
- invent features or refactors outside the task
- patch around a bad result without first updating the decision

## Exploration Policy

Exploration tasks:
- accept initial ambiguity
- must produce options, risks, and a proposed decision
- may include discardable spikes marked `[SPIKE] - no shipping`

## Implementation Policy

Implementation tasks:
- require a prior closed decision
- must define scope, constraints, and validation
- should be rejected or redirected if the decision is still ambiguous

## Hotfix Policy

Hotfix tasks:
- compress the decision step
- require an explicit incident, fix hypothesis, risk, and validation plan
- stay as narrow as possible
