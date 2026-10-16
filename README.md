# From Telemetry to Recovery

A local lab for evidence-backed incident investigation and controlled recovery.

Follow a worker-queue incident from recorded telemetry through investigation, exact-plan approval, controlled execution, and workload verification. Inspect the evidence and control code rather than relying only on the dashboard.

**This is a teaching implementation, not a production recovery controller or the prototype evaluated in the research.** The workload, clock, compatibility declaration, and actuator are synthetic. The local model inference, journal, policy checks, approval, and verification code actually run. No Kubernetes cluster or production service is accessed.

## Quick start: no model required

Requires Python 3.10 or later. The explicit rules baseline needs no third-party packages or cloud credentials:

```sh
git clone https://github.com/jayakumar-ramalingam/telemetry-to-recovery.git
cd telemetry-to-recovery
python3 server.py --provider rules
```

Open **http://127.0.0.1:8765**. Use exactly `127.0.0.1`, not `localhost`, because the write-origin check is strict. Stop the server with Control-C. Use `--port 8766` if necessary.

The interface labels this mode **Rules baseline · no LLM**. It is never a hidden fallback after a model error.

## Run with a real model

- **Local Llama through Ollama:** [LOCAL_SETUP.md](LOCAL_SETUP.md). Download the model before presenting; subsequent local inference does not require internet.
- **Optional AWS Bedrock:** [BEDROCK_SETUP.md](BEDROCK_SETUP.md). Requires your own authorized AWS access and incurs inference charges. It still acts only on the synthetic workload.

The investigator is read-only and receives no execution tools. Model failure, invalid output, or insufficient evidence stops the workflow; it does not silently switch providers and execute.

## Technical guides

- [Component walkthrough and demonstration sequence](LIVE_DEMO.md)
- [Implementation and proposed AWS architecture](ARCHITECTURE.md)

The workflow addresses four questions:

1. Does the evidence support attempting it?
2. Is the action permitted right now?
3. What actually happened during execution?
4. Did useful work recover?

## What actually executes

- Three logical roles, not three independent LLMs: detection and recovery controls run as Python code; local model mode uses one read-only Llama investigator. The workflow supervisor is code.
- The investigator receives selected observation/change events and versioned runbooks retrieved with local metadata/keyword matching. Injector fault labels, credentials, approvals, and execution receipts are excluded from that packet.
- Output validation checks JSON shape, allowed actions, and references. Independent scenario checks must also support the recovery proposal. A valid citation is not proof of a correct interpretation.
- The executor checks the allowlisted target, expected revision, compatibility declaration, fresh evidence, exact-plan approval, and active action before mutation.
- A local SQLite journal records the sequence. Update/delete triggers enforce append-only use through the database, and a hash chain helps detect changes relative to that database.
- Duplicate action IDs return an existing receipt without another simulated mutation, including concurrent calls within one process.
- Verification checks workload recovery separately from action completion. Replay reconstructs selected recorded state without performing recovery again.

## Demonstration sequence

1. Start a **Memory regression** run and establish the healthy workload contract.
2. **Inject release + fault** and **Collect incident evidence**.
3. **Run diagnostic agents**; inspect the investigator input and actual response.
4. **Build + evaluate plan**, then **Why not scale out?** to inspect a denied alternative.
5. **Approve this recovery**, then **Execute approved rollback**.
6. **Observe + verify recovery**; distinguish a completed action from a recovered workload.
7. **Retry the same action**, then **Replay recorded history**.
8. Start **Incomplete evidence**, repeat the investigation, and show execution remains blocked.

The local model may recommend an unsupported action or correctly refuse. Do not promise a particular response. The boundary being demonstrated is that required evidence checks still control execution.

## Tests

Offline tests with model test doubles:

```sh
python3 -m unittest -v test_engine.py test_ai.py test_ollama.py
```

Optional Bedrock SDK contract tests use Botocore Stubber, not a live AWS request:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-bedrock.txt
.venv/bin/python -m unittest -v test_engine.py test_ai.py test_ollama.py test_bedrock_sdk.py
```

Tests exercise missing evidence, bad model output, absent/expired approval, changed plans and revisions, stale observations, duplicates/concurrency, failed verification, incompatible rollback, active-action conflict, persistence, and fault-label isolation.

`check_local_model.py` runs actual local inference for both scenarios and saves generated evidence under ignored `data/` and `qa-local/` directories. It checks those control paths, not general model diagnostic accuracy.

## Boundaries

- No real application pods are restarted. The compatibility flag is a fixture declaration, not an integration test.
- The leading diagnosis is a hypothesis, not proof of a causal code defect. The local model has produced unsupported explanations in prior runs; independent checks stopped the missing-evidence case.
- The scale-out capacity estimate is illustrative, not a calibrated database model. Scaling is also outside the executor allowlist.
- Approval is a local button, not authenticated enterprise identity. Freshness and expiry use **scenario time**, which advances with scenario transitions rather than wall-clock time.
- SQLite and a hash chain do not provide secure immutability against someone who can replace the database.
- A process lock is not a distributed lease or fencing mechanism. Crash reconciliation between an external effect and its receipt is not fully implemented. This demo does not promise exactly-once external effects.
- Do not expose this server publicly, attach production tools, or supply administrator credentials. Only use synthetic data.
- The AWS architecture is proposed, not deployed or performance-tested by this repository. The lab does not reproduce the research's experiment or success rates.

## Browser QA and optional recording

`ui_smoke.mjs` checks the explicit rules baseline. `ui_local_check.mjs` runs the local-model path. These helpers create fresh browser contexts and generate ignored screenshots/evidence. They require Node.js, Playwright, and an installed compatible browser. Set `PLAYWRIGHT_MODULE` or `BROWSER_CHANNEL` if needed.

`record_demo.mjs` additionally requires FFmpeg. With the local-model server running:

```sh
DEMO_URL=http://127.0.0.1:8768 DEMO_RECORD_DIR=recordings-local node record_demo.mjs
```

The helper captures only a fresh demo browser, not the desktop, microphone, or existing browser profile. It produces a silent recording and refuses to overwrite an existing final recording. It rejects unsuccessful model runs rather than presenting them as successful AI demonstrations. Recordings, model weights, runtime binaries, local databases, and generated QA exports are not included in Git.
