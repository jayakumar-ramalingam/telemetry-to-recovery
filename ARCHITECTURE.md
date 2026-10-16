# Components and authority boundaries

## Implemented local lab

```text
Synthetic API -> Queue -> Workers -> Database
                   |
        observations + recorded changes
                   v
           SQLite incident journal
                   |
        selected evidence + runbooks
                   v
       Read-only local Llama investigator
                   |
       schema/reference validation
                   |
      independent scenario evidence checks
                   |
       bounded proposal + policy admission
                   |
           exact-plan human approval
                   |
       executor rechecks all preconditions
                   |
           simulated workload change
                   |
      independent workload verification
                   v
      results appended to incident journal
```

The roles are separate in responsibility, not three independent LLM processes. Detection, supervision, policy, execution, and verification are Python code. Only the read-only investigation invokes a model. The browser displays backend state; it does not manufacture approvals or observations.

| Component | Implementation | Responsibility |
| --- | --- | --- |
| Workload | `RecoveryDemo` in `engine.py` | Advances a repeatable synthetic incident and recovery fixture |
| History | `Journal` in `engine.py` | Appends events and checks a local hash chain |
| Context | `evidence_packet` in `ai_investigator.py` | Selects observation/change events without injector labels |
| Guidance | `retrieve_runbooks` and `runbooks/` | Retrieves owned, versioned guidance using metadata/keywords |
| Reasoning | `OllamaInvestigator` or `BedrockInvestigator` | Makes one bounded request without execution tools |
| Validation | `validate_output` plus independent scenario checks | Separates accepted JSON/references from permission to proceed |
| Authority | `Policy.evaluate`, `approve`, `execute` | Checks the operation, exact approved plan, and current scenario preconditions |
| Outcome | `verify_recovery` | Evaluates workload criteria separately from action completion |
| Replay | `replay` | Reconstructs selected recorded state without invoking the actuator |
| Interface | `server.py` and `web/` | Serves loopback-only UI/API with local write-token and origin checks |

## Four distinct kinds of information

- **Incident history:** recorded telemetry observations, changes, and investigation/action events.
- **Workflow state:** the current run stage, plan, approval, and execution status.
- **Runbook knowledge:** versioned guidance; not proof of current conditions.
- **Model context:** a selected input packet, not the entire history or unrestricted filesystem.

Missing observations stay missing. Neither valid JSON nor a real evidence ID establishes that the model interpreted an event correctly. The independent evidence criteria are specific to these scenarios, not a general-purpose semantic truth detector.

The **Input & decision** view compares the retained model input with its actual output and the current control decision. It does not present old model context as live telemetry. After approval, the optional DB-pressure challenge appends a new scenario observation and preserves the original context, plan, and approval. A preview is labeled as not yet executed; an actual execution attempt independently rechecks policy, records a denial, and persists the stopped state without applying a recovery mutation. No additional model call is made by that challenge.

## Proposed AWS reference architecture

**This mapping is a design for discussion, not deployed infrastructure or measured production behavior. There are no AWS deployment templates in this repository.**

| Concern | Proposed AWS implementation |
| --- | --- |
| Signals and changes | CloudWatch alarms through EventBridge, with collectors retrieving selected metrics/logs, Kubernetes events, and deployment/configuration history |
| Retained evidence | S3 incident evidence and referenced versions; retention controls must be configured explicitly |
| Durable workflow state | DynamoDB state and conditional writes; not inherently an immutable event store |
| Investigation | Bedrock inference, optionally specialist runtimes on AgentCore |
| Guidance | Versioned S3 runbooks, optionally indexed through Bedrock Knowledge Bases |
| Orchestration | Step Functions Standard workflow, code-based policy tasks, and authenticated exact-plan approval |
| Actuation | Narrow Lambda executor or EKS controller with scoped IAM/Kubernetes RBAC; appropriate SSM runbooks for supported targets |
| Verification | Separate checks using workload observations, with results written back to history |

The investigator does not hold infrastructure-write credentials. IAM and organizational policies constrain permissions, while application code checks incident-specific evidence, freshness, compatibility, approval, and target revision. These are complementary controls.

CloudWatch already retains historical telemetry. The added incident history connects selected observations to changes, proposals, approvals, and action outcomes; it does not imply that cloud telemetry contains only the present moment.

## Beyond the lab

Production implementation needs authenticated approvals, wall-clock expiry, protected retention, compatibility evidence, leases/fencing, external-effect reconciliation, failure testing, and workload-specific evaluation. More specialist agents do not automatically mean better diagnosis or independent evidence. Bound investigations, model/tool calls, retries, and elapsed time; escalate instead of expanding authority when those budgets expire.

Keep active runbook retrieval current without destroying versions referenced by past incidents. Reuse stable guidance where appropriate, not diagnoses or approvals based solely on similarity to an earlier incident.

## Design references

- [CloudWatch and EventBridge](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch-and-eventbridge.html)
- [Step Functions callback tasks](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html#connect-wait-token)
- [Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- [Bedrock Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [VoiceOPS reference project](https://github.com/mathisree26/VoiceOPS_AI)

The VoiceOPS reference informed discussion of cloud diagnostic wiring and runbook retrieval. This lab is a separate implementation; no source code from that project or its results are claimed here.
