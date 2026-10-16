# Bedrock investigator setup

## Current status

The application contains a Bedrock Converse integration, a versioned local runbook
retriever, response validation, and fail-closed supervision. A real model response
is displayed only after it is actually received and accepted. Test doubles are
used only in tests, never exposed as a demo provider.

No recording or AWS deployment is included in this repository. A Bedrock
demonstration requires working local AWS authentication, region, and model access.
Running Bedrock mode does not deploy the proposed AWS recovery architecture.

## Local environment

Use a terminal in the demo folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-bedrock.txt
```

Authenticate using your organization's existing AWS process. For an already
configured AWS IAM Identity Center profile, that may be:

```sh
aws sso login --profile YOUR_EXISTING_PROFILE
```

This application does not create AWS users, credentials, permissions, model
subscriptions, infrastructure, or accounts. Do not paste keys into the browser,
chat, source files, or recordings. The SDK uses your local credential chain.

## Start Bedrock mode

Replace the three placeholders with your existing profile, enabled region, and an
enabled Converse-compatible model ID or inference profile ID:

```sh
.venv/bin/python server.py --provider bedrock \
  --profile YOUR_EXISTING_PROFILE \
  --region YOUR_AWS_REGION \
  --model-id YOUR_ENABLED_MODEL_ID
```

Alternatively set `DEMO_BEDROCK_MODEL_ID` and `AWS_REGION` locally. Omit `--profile`
only if your approved default credential chain is the one you intend to use.
The model and region are intentionally not guessed by the application.

The server uses port 8765; add `--port 8766` if another demo is running. Open
`http://127.0.0.1:8765` (or your chosen port).

The application makes one bounded, non-streaming inference request per incident
investigation. Inference can incur AWS charges. Automatic SDK retries are disabled.
A timed-out request might still have reached the model; it is not automatically
retried. No other AWS resources are queried or modified by this implementation.

## Access boundary

The investigator needs `bedrock:InvokeModel` for the selected model/inference
profile and any underlying model resources required by that profile. Ask your AWS
administrator to scope the existing role appropriately. Do not use broad admin
credentials merely to run the demonstration.

The application instantiates only a `bedrock-runtime` client. It supplies no tool
definitions and exposes no shell, Kubernetes, database-write, or remediation API to
the model. The local executor applies only synthetic workload changes.

These are application boundaries, not a claim that any AWS profile supplied by a
user is automatically least-privileged. IAM enforcement remains a separate setup.

## What the investigator receives

1. Observation and change records for the synthetic `demo/workers` scope.
2. Versioned owned runbooks from `runbooks/`, selected using deterministic local
   metadata/keyword matching. This is not an AWS Bedrock Knowledge Base or vector RAG.
3. A response schema and explicit source-role instructions.

Injector fault labels, local AWS credentials/profile names, approvals, executor
receipts, and arbitrary filesystem contents are not included in the evidence packet.
The request is persisted as `agent.ai_request` for inspection. Use only synthetic
data with this teaching application.

## What is enforced after the response

- Strict JSON shape and length limits; no unknown fields such as shell commands.
- Only `rollback` or `escalate`; only the allowlisted `demo/workers` scope.
- Event IDs and runbook IDs must exist in the supplied input.
- A rollback needs both observation and change-history references and the matching
  memory-regression runbook.
- Independent scenario rules must also support the rollback. A valid-looking model
  answer cannot override missing memory evidence or contradictory workload evidence.
- Model uncertainty, invalid output, permission failure, missing configuration, or
  timeout stops the workflow. It does not silently fall back to rules and execute.
- Approval, revision/freshness checks, duplicate suppression, and recovery
  verification remain independent of the model.

Reference validation is not semantic fact checking. Prompt instructions and JSON
validation do not prove resistance to every prompt-injection attack. Test bad
outputs, conflicting evidence, and unavailable dependencies before expanding scope.

## Record the real-model version

Complete a full successful Bedrock run and an incomplete-evidence run first.
Inspect the AI investigator tab and the exported `agent.ai_response` events. They
must show `model_invoked: true`; a successful path must also show `validated: true`.

Then run the recording helper with a new output directory:

```sh
DEMO_RECORD_DIR=recordings-bedrock node record_demo.mjs
```

The helper will refuse to label an unconfigured provider or failed model run as a
successful Bedrock recording. It records only the local browser page, not your
desktop, authentication flow, or AWS credentials. Narrate the resulting MP4 in
person. Its synthetic scenario clock is not a production recovery benchmark.

## Explicit offline baseline

```sh
python3 server.py --provider rules
```

This mode requires no cloud access. The UI labels it **Rules baseline · no LLM**.
It is an explicit mode switch, never a hidden fallback after a model failure.

## Tests

```sh
python3 -m unittest -v test_engine.py test_ai.py
```

All these tests run without AWS. Their model responses are test doubles, not proof
of live model performance. The optional SDK contract test uses Botocore Stubber:

```sh
.venv/bin/python -m unittest -v test_bedrock_sdk.py
```

It validates the real SDK request/response shape without sending a network request.

## References

- [AWS Converse guide](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
- [Boto3 Converse API](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html)
- [VoiceOps diagnostic architecture reference](https://github.com/mathisree26/VoiceOPS_AI/blob/main/cloudformation/README.md)

The application code and synthetic runbooks here are a separate teaching
implementation. No VoiceOps source code or research experiment results are claimed
as part of this implementation.
