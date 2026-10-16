# Live demo: what to show and say

Allow approximately 11 minutes in the middle of the talk. The original local recording is a backup strategy, not a Git-tracked artifact. Prepare your own tested recording or screenshots on the presentation machine.

## State the boundary once

> The workload and actuator are synthetic so we can reproduce the incident safely. The local model, evidence handling, independent checks, approval, and journal are running here. This is not a live Kubernetes rollback or the research benchmark.

Use three prepared views: browser for progression, terminal for selected exported events, and editor for two short code excerpts. Do not expose a personal desktop, unrelated tabs, credentials, or raw dumps too small to read.

## Before the session

1. Follow [LOCAL_SETUP.md](LOCAL_SETUP.md), download the model, and run both scenario checks on this laptop.
2. Start Ollama and the web server in advance. Rehearse a complete inference to warm the model.
3. Open `http://127.0.0.1:8768` and select **Memory regression**, then **New run**.
4. Prepare `evidence_packet` in `ai_investigator.py` and `Policy.evaluate` in `engine.py` in the editor.
5. Keep backup screenshots/recording available. If inference fails, explain the stopped workflow. Do not bypass the checks or silently switch to a rules baseline.

## Part A: investigation and controlled recovery, about seven minutes

### 1. Establish healthy behavior

Show **Investigation**. Arrivals are 120 jobs/s, processing capacity is 140, and the oldest queued work is around four seconds old.

> We have processing headroom. The question is not just whether workers are running, but whether they can keep up.

### 2. Introduce the incident

Click **Inject release + fault**, then **Collect incident evidence**. Show rising memory, restarts, queue age, and latency.

In **Event journal**, expand one `change.recorded` event and a relevant `telemetry.sample`. The button advances a fixture, not a real deployment.

> The release and the memory increase are separate observations. Their timing supports an investigation; it does not prove the exact code defect.

### 3. Run actual inference

Click **Run diagnostic agents**. While waiting, show the prepared evidence-building code or records already open. The server serializes this investigation under its local lock; do not depend on a second live API read completing during inference.

After the response arrives, show **AI investigator**: provider, model, proposed action, evidence/runbook references, unknowns, latency, and tokens.

> This is the model's actual structured explanation, not hidden chain of thought. It can suggest a bounded rollback trial. It cannot approve or execute it, and valid references do not prove its interpretation.

The local lab has one LLM investigator. Other roles are code, not independently running LLM specialists.

### 4. Inspect the action boundary

Click **Build + evaluate plan** and show **Action contract**. Point to the target, expected revision, action ID, evidence, and approval requirement. Briefly show `Policy.evaluate` in the editor.

Click **Why not scale out?** before approval. Show the denied alternative.

> This action exceeds the allowlist and fails the scenario's downstream-pressure check. The capacity estimate is illustrative. The important point is that a plausible suggestion does not create permission.

### 5. Approve, execute, and verify separately

Click **Approve this recovery**, then **Execute approved rollback**. In the journal, show the approval and action receipt. Only then click **Observe + verify recovery**.

> The operation completed. We have not yet established that useful processing recovered.

Show the five verification checks: queue age, processing capacity, latency, no additional restarts, and database pressure. The 120-second observation and final 30-second checks are **scenario time**, advanced by the fixture, not measured real-time recovery performance.

### 6. Retry and replay

Click **Retry the same action**, then **Replay recorded history**. Show that only one simulated mutation occurred and replay causes no additional action.

> A repeated request returns the existing receipt. Replay reconstructs recorded state without replaying the external effect. This local mechanism is not a complete distributed exactly-once implementation.

## Part B: insufficient evidence, about four minutes

Select **Incomplete evidence**, click **New run**, then repeat **Inject release + fault**, **Collect incident evidence**, and **Run diagnostic agents**.

Show missing incident memory observations and the stopped workflow. Inspect the actual model response. It may recommend rollback or correctly refuse; neither response is guaranteed.

> In the earlier example, an action was outside the operational boundary. Here the evidence itself is insufficient. Even if the model recommends rollback, the independent checks prevent execution.

Show the current run's event history and confirm it contains no `change.applied` event. If using a prior recorded model error, label it as a prior run rather than implying it just happened live.

## Terminal view: inspect real records

Keep output short. On a machine with `curl` and `jq`, for example:

```sh
curl -fsS http://127.0.0.1:8768/api/export | jq '.integrity'
curl -fsS http://127.0.0.1:8768/api/export | jq '.events[] | select(.kind == "change.recorded" or .kind == "approval.granted" or .kind == "change.applied") | {seq, kind, payload}'
```

These GET requests inspect the current run without mutation. If `jq` is unavailable, use the browser's **Event journal** or **Export incident evidence** instead. Read/export views may wait while inference holds the local workflow lock.

## Handling an unsuccessful live run

- **Model timeout, invalid response, or refusal:** show the stop; do not keep rerunning indefinitely to obtain the answer you wanted.
- **Unexpected supported-case behavior:** inspect the recorded evidence, then switch to a clearly labeled prior run if needed.
- **Venue network failure:** local inference works offline after installation/download; optional Bedrock mode does not.
- **Browser or laptop trouble:** use prepared screenshots or a recording and state that it is a backup.

Close the demo with the four questions: did the evidence justify the attempt, was it permitted, what happened, and did useful work recover?
