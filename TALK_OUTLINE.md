# From Telemetry to Recovery
## Building Self-Healing Cloud Systems with Multi-Agent AI

Days of Data Orlando. **16 slides, 50 minutes including an 11-minute live demo, followed by 10 minutes Q&A.** The times are rehearsal targets, not measured delivery duration. Target approximately 5,500-5,800 spoken words including demo narration, then rehearse with real inference waits and window switching.

Follow one worker-queue incident throughout. Keep research findings, a proposed AWS deployment design, and implemented local-demo behavior distinct.

The recurring questions:

1. Does the evidence support attempting it?
2. Is the action permitted right now?
3. What actually happened during execution?
4. Did useful work recover?

## Act 1: establish the problem, 0-9 minutes

### 1. A release goes out. The queue stops draining. (0-1)

Open with rising memory, restarts, and queue age after a worker release. Requests still succeed, but processing falls behind. State the three evidence levels briefly.

**Point:** A running service is not necessarily a functioning workload.

### 2. Same symptoms, different explanations (1-4)

Show API, queue, workers, and database. Compare a worker regression, increased traffic/larger payloads, downstream slowness, changed limits, and node pressure. Explain why their appropriate interventions differ.

**Point:** Detecting degradation does not establish which action is justified.

### 3. Define what recovery means (4-6)

Set the workload contract: capacity exceeds arrivals, queue age falls, latency meets the limit, no additional restarts, and acceptable database pressure. Introduce the four questions.

**Point:** Define success before choosing the fix.

### 4. Build the incident history (6-9)

Connect baseline observations, changes, resource behavior, and dependency signals. Retain timestamps, versions, references, and explicit evidence gaps.

**Point:** Reconstruct the recorded incident without pretending the record is complete.

## Act 2: design the investigation, 9-19 minutes

### 5. Bounded roles, shared evidence (9-12)

Introduce specialist investigation roles and a supervisor. Explain focused queries and competing hypotheses, but acknowledge that shared incomplete evidence can produce shared errors. Distinguish history, workflow state, runbook knowledge, and model context.

**Point:** Roles organize reasoning; they do not grant authority or guarantee correctness.

### 6. Put the design on AWS (12-16)

Present the proposed mapping: CloudWatch/change collection, S3 retained evidence, DynamoDB state, Bedrock reasoning/runbook retrieval, Step Functions orchestration, scoped execution, and separate verification. Focus on retained history and authority transitions.

**Point:** Durable orchestration and permission boundaries surround the model.

### 7. Turn evidence into a bounded proposal (16-19)

Assemble a limited packet, compare explanations, retrieve guidance, state unknowns, and propose one recovery trial. Distinguish response-format validation, reference validation, and a supported interpretation.

**Point:** A proposal needs evidence and preconditions, not just persuasive language.

## Act 3: live demonstration, 19-30 minutes

### 8. Investigate, approve, execute, verify (19-26)

Use browser, terminal, and prepared code excerpts. Show input records, actual inference, independent policy, denied excessive scale-out, exact-plan approval, receipt, workload verification, duplicate suppression, and replay. Disclose synthetic workload/time/actuator and one actual read-only LLM investigator.

**Point:** The model proposes; independent controls determine what executes.

### 9. Remove evidence and challenge the boundary (26-30)

Run incomplete evidence. Show the actual response, whether it proposes rollback or refuses. Execution must remain blocked. Contrast insufficient evidence with an operational restriction. A prior recorded model mistake is backup evidence, not a promised live response.

**Point:** Safety cannot depend on the model always making the right recommendation.

## Act 4: engineer controlled recovery, 30-46 minutes

### 10. Approve an exact operation (30-33)

Define target, expected revision, evidence, expiry, compatibility, action identity, exact-plan approval, and scoped executor credentials.

**Point:** Approve this operation against these conditions, not general permission to fix things.

### 11. A timeout does not mean nothing happened (33-36)

Explain lost acknowledgements, partial completion, reconciliation, action identity, receipts, duplicate suppression, and ownership. Distinguish the lab's local lock from production leases/fencing and external-effect reconciliation.

**Point:** Resolve uncertain execution before retrying a potentially completed action.

### 12. Verify useful work (36-39)

Compare command completion with recovering queue age, capacity, latency, restarts, and dependency headroom. Define verification failure and escalation.

**Point:** Execution success and recovery success are separate results.

### 13. Rollback is not an undo button (39-43)

Ask whether the old worker can process work produced by the new revision. Separate software rollback, compensation, unfinished work, and historical replay without side effects.

**Point:** Restoring an old deployment does not automatically restore business state.

### 14. Protect the recovery controller (43-46)

Cover evidence lag, unavailable models, competing investigations, and excessive tool use. Group alerts; bound calls, retries, reads, and elapsed time. Reuse stable guidance, not old diagnoses/approvals. Retire obsolete runbooks from active retrieval while preserving referenced versions.

**Point:** The controller needs its own reliability, security, and cost controls.

## Act 5: validate and adopt, 46-50 minutes

### 15. Test the recovery system itself (46-48)

Evaluate evidence, diagnosis, authorization, execution, and verification separately. Exercise missing/misleading evidence, stale approvals, duplicate requests, unavailable dependencies, and unsuccessful recovery. Keep controlled research evidence separate from lab observations and future production validation.

**Point:** Correct refusal or escalation can be a successful outcome.

### 16. Start with one bounded recovery (48-50)

One service, one action class, shadow mode, human-approved execution, then measured expansion. Name limits: novel failures, broken telemetry, and unfamiliar services. Return to the incident and four questions.

> Let the AI investigate. Keep the authority in the engineering system.

## Q&A (50-60)

Leave slide 16 visible. Keep a tested recording or selected screenshots available as backup. If running late, shorten architecture detail and the list of competing explanations; preserve uncertain execution and workload verification.
