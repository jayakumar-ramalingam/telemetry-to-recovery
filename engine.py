"""Synthetic workload, optional model investigation, and a local incident journal.

This is a teaching implementation, not Kubernetes automation or the research prototype.
Only explicit model mode calls a model. No shell or cluster tools are exposed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ai_investigator import evidence_packet


class DemoError(Exception):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Journal:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
            kind TEXT NOT NULL, scenario_s INTEGER NOT NULL, recorded_at TEXT NOT NULL,
            payload TEXT NOT NULL, previous_hash TEXT NOT NULL, digest TEXT NOT NULL
          );
          CREATE TRIGGER IF NOT EXISTS no_event_update BEFORE UPDATE ON events
            BEGIN SELECT RAISE(ABORT, 'Incident events are append-only'); END;
          CREATE TRIGGER IF NOT EXISTS no_event_delete BEFORE DELETE ON events
            BEGIN SELECT RAISE(ABORT, 'Incident events are append-only'); END;
        """)
        self.db.commit()

    def append(self, run, kind, seconds, payload):
        prior = self.db.execute("SELECT digest FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = prior[0] if prior else "0" * 64
        at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        raw = canonical(payload)
        digest = hashlib.sha256(canonical([previous, run, kind, seconds, at, raw]).encode()).hexdigest()
        cur = self.db.execute(
            "INSERT INTO events(run_id,kind,scenario_s,recorded_at,payload,previous_hash,digest) VALUES(?,?,?,?,?,?,?)",
            (run, kind, seconds, at, raw, previous, digest))
        self.db.commit()
        return cur.lastrowid

    def events(self, run):
        return [dict(row, payload=json.loads(row["payload"])) for row in
                self.db.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq", (run,))]

    def latest_run(self):
        row = self.db.execute("SELECT run_id FROM events WHERE kind='run.started' ORDER BY seq DESC LIMIT 1").fetchone()
        return row[0] if row else None

    def verify(self):
        previous = "0" * 64
        count = 0
        for row in self.db.execute("SELECT * FROM events ORDER BY seq"):
            digest = hashlib.sha256(canonical([
                previous, row["run_id"], row["kind"], row["scenario_s"],
                row["recorded_at"], row["payload"]]).encode()).hexdigest()
            if row["previous_hash"] != previous or digest != row["digest"]:
                return {"valid": False, "events_checked": count}
            previous = row["digest"]
            count += 1
        return {"valid": True, "events_checked": count}


class DetectionAgent:
    """Reads observations only. The injector's fault label is never an input."""
    @staticmethod
    def run(events):
        samples = [e for e in events if e["kind"] == "telemetry.sample"]
        last = samples[-1]
        m = last["payload"]
        symptoms = []
        if m["queue_age_s"] > 30:
            symptoms.append("Oldest queued work exceeds the 30-second contract")
        if m["restarts"] >= 3:
            symptoms.append("Worker restarts increased while progress fell")
        return {"status": "anomaly" if symptoms else "normal", "symptoms": symptoms,
                "evidence": [last["seq"]], "agent": "Fault detection"}


class ReasoningAgent:
    @staticmethod
    def run(events):
        samples = [e for e in events if e["kind"] == "telemetry.sample"]
        changes = [e for e in events if e["kind"] == "change.recorded"]
        old = [e for e in samples if e["payload"]["revision"] == "worker:v1"]
        new = [e for e in samples if e["payload"]["revision"] == "worker:v2"]
        last = samples[-1]
        missing = not last["payload"]["memory_observed"]
        if missing or not old or not new or not changes:
            return {"agent": "Root-cause reasoning", "status": "insufficient_evidence",
                    "summary": "Memory evidence is incomplete. A release correlation is not enough to authorize rollback.",
                    "evidence": [last["seq"]], "hypotheses": [
                        {"name": "Worker regression", "verdict": "Unresolved", "why": "Missing memory series prevents the before/after check."},
                        {"name": "Downstream saturation", "verdict": "Unresolved", "why": "Current DB utilization does not explain the missing observations."}],
                    "unknowns": ["Worker memory profile across the release", "Whether the incident has another contributing cause"]}
        peak = max(e["payload"]["memory_mb"] for e in new)
        base = max(e["payload"]["memory_mb"] for e in old)
        m = last["payload"]
        baseline_input = sum(e["payload"]["input_rps"] for e in old) / len(old)
        peak_input = max(e["payload"]["input_rps"] for e in new)
        traffic_surge = peak_input > baseline_input * 1.25
        supported = peak > 2 * base and m["restarts"] >= 3 and m["db_pct"] < 75 and not traffic_surge
        return {"agent": "Root-cause reasoning", "status": "supported_hypothesis" if supported else "insufficient_evidence",
                "summary": "Worker v2 is the leading regression hypothesis; evidence supports a bounded rollback trial." if supported else "No hypothesis meets the action criteria.",
                "evidence": [old[-1]["seq"], changes[-1]["seq"], max(new, key=lambda e: e["payload"]["memory_mb"])["seq"], last["seq"]],
                "hypotheses": [
                    {"name": "Worker regression", "verdict": "Supported", "why": f"Memory rose from at most {base} MB to {peak} MB after v2; restarts followed."},
                    {"name": "Traffic surge", "verdict": "Supported" if traffic_surge else "Not supported", "why": f"Baseline input {baseline_input:g} jobs/s; incident peak {peak_input:g} jobs/s."},
                    {"name": "Database saturation", "verdict": "Not supported", "why": f"Current database utilization is {m['db_pct']}%, below the scenario's saturation threshold."}],
                "unknowns": ["The exact code defect is not established", "Other causes remain possible outside the captured evidence"]}


class Policy:
    """Enforced by the executor too; text in a proposal is not authority."""
    @staticmethod
    def evaluate(plan, state, approved=False):
        last = state["metrics"][-1]
        diagnosis = state.get("diagnosis") or {}
        tests = [
            ("Target is allowlisted", plan.get("target") == "demo/workers"),
            ("Observed revision still matches", plan.get("expected_revision") == state["revision"]),
            ("Evidence is complete and at most 30 scenario seconds old", last["memory_observed"] and 0 <= state["scenario_s"] - plan.get("observed_s", -999) <= 30),
            ("Diagnosis meets the evidence rule", diagnosis.get("status") == "supported_hypothesis"),
            ("Compatible prior revision exists", plan.get("to_revision") == "worker:v1" and state["compatible"]),
            ("No other recovery owns this target", state.get("active_action") in (None, plan.get("action_id"))),
            ("Action is an allowed rollback", plan.get("kind") == "rollback"),
            ("Plan is limited to one target", plan.get("max_targets") == 1),
        ]
        if state.get("ai_required"):
            report = state.get("ai_report") or {}
            analysis = report.get("analysis") or {}
            tests.extend([
                ("Model output passed structural and reference checks", report.get("validated") is True and report.get("model_invoked") is True),
                ("Model proposes this bounded rollback", analysis.get("status") == "supported_hypothesis" and analysis.get("proposed_action") == "rollback" and analysis.get("target") == "demo/workers"),
            ])
        if plan.get("kind") == "scale":
            projected = round(last["db_pct"] * plan.get("replicas", 9) / state["replicas"])
            tests.append((f"Projected DB utilization {projected}% stays below 80%", projected < 80))
        if approved:
            approval = state.get("approval") or {}
            tests.extend([
                ("Downstream DB remains below the 80% stop threshold", last["db_pct"] < 80),
                ("Human approved this exact plan", approval.get("plan_hash") == hashlib.sha256(canonical(plan).encode()).hexdigest()),
                ("Approval has not expired", 0 <= state["scenario_s"] - approval.get("at_s", -999) <= 60),
            ])
        return {"allowed": all(ok for _, ok in tests),
                "checks": [{"name": name, "passed": bool(ok)} for name, ok in tests]}


class RecoveryDemo:
    def __init__(self, db_path, investigator=None):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.journal = Journal(db_path)
        self.lock = threading.RLock()
        self.investigator = investigator
        self.run_id = self.journal.latest_run()
        if not self.run_id:
            self.new_run("memory")
        else:
            previous = self.load().get("ai_config", {"provider": "rules", "model_id": "None"})
            wanted = investigator.public_config() if investigator else {"provider": "rules", "model_id": "None"}
            if any(previous.get(key) != wanted.get(key) for key in ["provider", "model_id", "region"]):
                self.new_run("memory")

    def emit(self, kind, seconds, payload):
        return self.journal.append(self.run_id, kind, seconds, payload)

    def save(self, state):
        self.emit("projection.checkpoint", state["scenario_s"], state)

    def state(self):
        events = self.journal.events(self.run_id)
        checkpoints = [e for e in events if e["kind"] == "projection.checkpoint"]
        state = copy.deepcopy(checkpoints[-1]["payload"])
        state["journal"] = [{"seq": e["seq"], "kind": e["kind"], "scenario_s": e["scenario_s"], "payload": e["payload"]}
                            for e in events if e["kind"] != "projection.checkpoint"]
        state["integrity"] = self.journal.verify()
        return state

    def load(self):
        state = self.state()
        for k in ["journal", "integrity"]:
            state.pop(k, None)
        return state

    def sample(self, state, second, memory, queue, latency, restarts, db=58, throughput=72, observed=True):
        metric = {"scenario_s": second, "memory_mb": memory, "queue_age_s": queue,
                  "p95_ms": latency, "restarts": restarts, "db_pct": db,
                  "throughput": throughput, "input_rps": 120,
                  "memory_observed": observed, "revision": state["revision"]}
        seq = self.emit("telemetry.sample", second, metric)
        state["metrics"].append(dict(metric, event_seq=seq))
        state["scenario_s"] = second

    def new_run(self, scenario):
        if scenario not in ("memory", "gap"):
            raise DemoError("Unknown scenario")
        with self.lock:
            self.run_id = str(uuid.uuid4())[:8]
            state = {"run_id": self.run_id, "scenario": scenario, "stage": "baseline", "scenario_s": 0,
                     "revision": "worker:v1", "replicas": 3, "compatible": True, "metrics": [],
                     "detection": None, "diagnosis": None, "plan": None, "policy": None,
                     "rule_diagnosis": None, "ai_report": None, "ai_packet": None,
                     "ai_required": self.investigator is not None,
                     "ai_config": self.investigator.public_config() if self.investigator else {
                         "provider": "rules", "model_id": "None", "configured": False,
                         "role": "Deterministic baseline; not an LLM"},
                     "approval": None, "execution": None, "verification": None,
                     "condition_change": None, "execution_policy": None,
                     "execution_policy_phase": None, "execution_blocked": False,
                     "active_action": None, "replay": None, "denial": None,
                     "headline": "Healthy baseline. The next release changes the worker.",
                     "explanation": "120 jobs/s enter the queue. Three workers have 140 jobs/s of processing capacity. Oldest work is 4 seconds old."}
            self.emit("run.started", 0, {"scenario": scenario, "synthetic": True,
                      "agents": "Read-only model investigator + independent Python controls" if self.investigator else "deterministic Python baseline",
                      "ai_config": state["ai_config"], "purpose": "teaching demo, separate from evaluated research prototype"})
            self.emit("topology.recorded", 0, {"path": ["API", "Queue", "Workers", "Database"], "target": "demo/workers"})
            for t in range(0, 60, 10):
                self.sample(state, t, 112 + t // 10 * 2, 4, 180, 0, db=40, throughput=140)
            self.save(state)
            return self.state()

    def next(self):
        with self.lock:
            s = self.load()
            stage = s["stage"]
            if stage == "baseline":
                s["revision"] = "worker:v2"
                self.emit("change.recorded", 60, {"target": "demo/workers", "from": "worker:v1", "to": "worker:v2", "change_id": "release-42"})
                for i, memory in enumerate([150, 205, 265, 340, 415, 478, 210, 370, 490]):
                    self.sample(s, 70 + i * 10, memory if s["scenario"] == "memory" else None,
                                8 + i * 4, 220 + i * 88, min(3, i // 2),
                                observed=s["scenario"] == "memory")
                s.update(stage="incident", headline="Pods restart. Work gets older. What changed first?",
                         explanation="Worker v2 is active. Queue age is 40 seconds; processing capacity has fallen to 72 jobs/s. Input is still 120 jobs/s.")
            elif stage == "incident":
                allowed = {"telemetry.sample", "change.recorded", "topology.recorded"}
                evidence = [e["seq"] for e in self.journal.events(self.run_id) if e["kind"] in allowed]
                self.emit("evidence.collected", s["scenario_s"], {"event_refs": evidence, "injector_labels_included": False,
                          "note": "Observation and change events only; fault labels are excluded from agent inputs."})
                s.update(stage="evidence", headline="Preserve the sequence, not just the latest reading.",
                         explanation="The evidence window includes baseline, release, memory, restarts, queue age, and database load. Fault-injector labels are excluded.")
            elif stage == "evidence":
                observed_events = [e for e in self.journal.events(self.run_id)
                                   if e["kind"] in {"telemetry.sample", "change.recorded", "topology.recorded"}]
                s["detection"] = DetectionAgent.run(observed_events)
                s["diagnosis"] = ReasoningAgent.run(observed_events)
                s["rule_diagnosis"] = copy.deepcopy(s["diagnosis"])
                s["ai_packet"] = evidence_packet(observed_events)
                self.emit("agent.detection", s["scenario_s"], s["detection"])
                self.emit("runbooks.retrieved", s["scenario_s"], {
                    "method": "local metadata and keyword retrieval; not a Bedrock Knowledge Base",
                    "runbooks": [{k: b[k] for k in ["id", "owner", "revision", "content_sha256", "retrieval_score"]}
                                 for b in s["ai_packet"]["runbooks"]]})
                if self.investigator:
                    self.emit("agent.ai_request", s["scenario_s"], s["ai_packet"])
                    report = self.investigator.investigate(s["ai_packet"])
                    s["ai_report"] = report
                    self.emit("agent.ai_response", s["scenario_s"], report)
                    if report.get("validated"):
                        analysis = report["analysis"]
                        supported = (s["rule_diagnosis"]["status"] == "supported_hypothesis" and
                                     analysis["status"] == "supported_hypothesis" and analysis["proposed_action"] == "rollback")
                        s["diagnosis"] = {"agent": "Model investigation + independent checks",
                            "status": "supported_hypothesis" if supported else "insufficient_evidence",
                            "summary": analysis["summary"] if supported else "Investigation did not satisfy both the model proposal and independent evidence checks. Escalate.",
                            "evidence": analysis["evidence"], "unknowns": analysis["unknowns"],
                            "hypotheses": [{"name": h["name"], "why": h["why"],
                                            "verdict": h["verdict"].replace("_", " ").capitalize()}
                                           for h in analysis["hypotheses"]]}
                    else:
                        s["diagnosis"] = dict(s["rule_diagnosis"], status="insufficient_evidence",
                            summary="Model investigation is unavailable or its output was rejected. No automatic fallback to execution.")
                self.emit("agent.diagnosis", s["scenario_s"], s["diagnosis"])
                if s["diagnosis"]["status"] == "insufficient_evidence":
                    s.update(stage="stopped", headline="STOP: incomplete evidence. No recovery action.",
                             explanation="The supervisor escalates for investigation. The timeout does not turn uncertainty into permission.")
                    self.emit("supervisor.escalated", s["scenario_s"], {"reason": "insufficient_evidence", "writes_executed": 0})
                    if s.get("ai_report") and not s["ai_report"].get("validated"):
                        s.update(headline="STOP: AI investigation unavailable or rejected.",
                                 explanation="No fallback is allowed to approve or execute recovery. See the AI investigator tab for the recorded result.")
                else:
                    s.update(stage="diagnosed", headline="A supported hypothesis, not a certainty score.",
                             explanation="The model's proposal also passed independent scenario checks. It is a bounded rollback trial, not proof of the code defect." if self.investigator else "The rule compares before/after memory, restarts, workload input, and downstream load. It supports a bounded rollback trial; it does not identify the code defect.")
            elif stage == "diagnosed":
                s["plan"] = {"action_id": "rollback-" + self.run_id, "kind": "rollback", "target": "demo/workers",
                             "expected_revision": "worker:v2", "to_revision": "worker:v1", "observed_s": s["scenario_s"],
                             "evidence_refs": s["diagnosis"]["evidence"], "max_targets": 1, "verification_window_s": 120,
                             "stop_if": "revision changed, evidence stale, compatibility unknown, DB > 80%, or recovery criteria fail"}
                if s.get("ai_required"):
                    s["plan"].update(ai_response_sha256=s["ai_report"]["response_sha256"],
                                     runbook_refs=s["ai_report"]["analysis"]["runbook_refs"])
                s["policy"] = Policy.evaluate(s["plan"], s)
                self.emit("recovery.proposed", s["scenario_s"], s["plan"])
                self.emit("policy.evaluated", s["scenario_s"], s["policy"])
                s.update(stage="planned", headline="An allowed plan still needs approval.",
                         explanation="One workload. A known prior revision. Fresh evidence. Compatibility checked. The executor has no shell or arbitrary cluster access.")
            else:
                raise DemoError("Use the explicit approval, execution, or verification control for this stage")
            self.save(s)
            return self.state()

    def approve(self, operator="Presenter"):
        with self.lock:
            s = self.load()
            if s["stage"] != "planned" or not Policy.evaluate(s["plan"], s)["allowed"]:
                raise DemoError("No admissible plan is awaiting approval")
            s["approval"] = {"operator": operator, "at_s": s["scenario_s"],
                             "plan_hash": hashlib.sha256(canonical(s["plan"]).encode()).hexdigest()}
            s["denial"] = None
            s["execution_policy"] = None
            s["execution_policy_phase"] = None
            s["execution_blocked"] = False
            self.emit("approval.granted", s["scenario_s"], s["approval"])
            s.update(stage="approved", headline="Approval is bound to this exact plan.",
                     explanation="The executor will recheck revision, evidence, ownership, and approval before applying the action. An edited plan needs new approval.")
            self.save(s)
            return self.state()

    def challenge_db_pressure(self):
        """Append a scenario observation after approval; never rewrite its evidence."""
        with self.lock:
            s = self.load()
            if s["stage"] != "approved" or not s.get("approval") or not s.get("plan"):
                raise DemoError("Approve a plan before changing the downstream conditions")
            if s.get("condition_change"):
                raise DemoError("This run already contains a condition change; start a new run to repeat it")
            last = s["metrics"][-1]
            before = last["db_pct"]
            self.sample(s, s["scenario_s"] + 5, last["memory_mb"], last["queue_age_s"],
                        last["p95_ms"], last["restarts"], db=90,
                        throughput=last["throughput"], observed=last["memory_observed"])
            s["condition_change"] = {
                "kind": "db_pressure", "before_db_pct": before, "after_db_pct": 90,
                "observation_ref": s["metrics"][-1]["event_seq"],
                "approved_plan_hash": s["approval"]["plan_hash"],
                "source": "explicit synthetic scenario control",
            }
            self.emit("scenario.condition_changed", s["scenario_s"], s["condition_change"])
            s["execution_policy"] = Policy.evaluate(s["plan"], s, approved=True)
            s["execution_policy_phase"] = "preview"
            self.emit("execution.preview", s["scenario_s"],
                      {"action_id": s["plan"]["action_id"], **s["execution_policy"]})
            s.update(headline="Conditions changed after approval.",
                     explanation="A new scenario observation raises DB utilization to 90%. The model input, approved plan, and approval are unchanged. Attempt execution to see the executor recheck the current conditions.")
            self.save(s)
            return self.state()

    def execute(self):
        with self.lock:
            s = self.load()
            if not s.get("plan"):
                raise DemoError("No proposed action")
            action_id = s["plan"]["action_id"]
            receipts = [e for e in self.journal.events(self.run_id) if e["kind"] == "action.completed" and e["payload"]["action_id"] == action_id]
            if receipts:
                self.emit("action.duplicate_suppressed", s["scenario_s"], {"action_id": action_id, "original_receipt": receipts[-1]["seq"], "new_mutations": 0})
                s["duplicate"] = "Same action ID received again. Original receipt returned; no second mutation."
                self.save(s)
                return self.state()
            policy = Policy.evaluate(s["plan"], s, approved=True)
            s["execution_policy"] = policy
            s["execution_policy_phase"] = "execution"
            self.emit("execution.preconditions_checked", s["scenario_s"],
                      {"action_id": action_id, **policy})
            if s["stage"] != "approved" or not policy["allowed"]:
                self.emit("action.denied", s["scenario_s"], policy)
                if s["stage"] == "approved":
                    s.update(stage="stopped", execution_blocked=True,
                             headline="STOP: execution preconditions failed.",
                             explanation="The executor rejected the approved plan against current conditions. No recovery mutation occurred. Start a new investigation rather than bypassing the failed checks.")
                self.save(s)
                raise DemoError("Executor refused the action: approval or preconditions failed")
            s["active_action"] = action_id
            self.emit("action.started", s["scenario_s"], {"action_id": action_id, "target": "demo/workers"})
            s["revision"] = "worker:v1"
            self.emit("change.applied", s["scenario_s"] + 5, {"action_id": action_id, "target": "demo/workers", "revision": "worker:v1", "synthetic_actuator": True})
            s["scenario_s"] += 5
            s["execution"] = {"action_id": action_id, "revision": "worker:v1", "mutations": 1}
            self.emit("action.completed", s["scenario_s"], s["execution"])
            s.update(stage="executed", headline="The action completed. Recovery is not yet proven.",
                     explanation="The simulated actuator has restored worker v1. We still need to see sustained workload progress and healthy downstream behavior.")
            self.save(s)
            return self.state()

    def verify_recovery(self, fail=False):
        with self.lock:
            s = self.load()
            if s["stage"] != "executed":
                raise DemoError("Execute a recovery before verifying it")
            start = s["scenario_s"]
            for i in range(1, 13):
                self.sample(s, start + i * 10, 120 + i % 3, 40 if fail else max(4, round(40 - i * 35 / 12)),
                            930 if fail else max(185, 924 - i * 90), 3,
                            db=83 if fail else 56, throughput=70 if fail else 155)
            recent = s["metrics"][-3:]
            checks = [
                ("Queue age below 30 s across the final 30 s", all(m["queue_age_s"] < 30 for m in recent)),
                ("Processing capacity above arrival rate", all(m["throughput"] > m["input_rps"] for m in recent)),
                ("End-to-end p95 below 300 ms", all(m["p95_ms"] < 300 for m in recent)),
                ("No additional worker restarts", all(m["restarts"] == 3 for m in recent)),
                ("DB utilization below 80%", all(m["db_pct"] < 80 for m in recent)),
            ]
            passed = all(ok for _, ok in checks)
            s["verification"] = {"passed": passed, "observed_window_s": 120,
                                 "final_stable_window_s": 30, "checks": [{"name": n, "passed": ok} for n, ok in checks]}
            s["active_action"] = None
            self.emit("recovery.verified" if passed else "recovery.failed", s["scenario_s"], s["verification"])
            s.update(stage="verified" if passed else "stopped", headline="Recovery verified against the workload contract." if passed else "STOP: the action ran, but recovery failed.",
                     explanation="120 scenario seconds observed. The final 30 seconds meet all five checks. Action completion and recovery success have separate receipts." if passed else "Do not loop through increasingly aggressive fixes. Escalate with the failed checks and recorded action.")
            self.save(s)
            return self.state()

    def unsafe_scale(self):
        with self.lock:
            s = self.load()
            if s["stage"] != "planned":
                raise DemoError("Compare alternatives while the plan awaits approval")
            alternative = dict(s["plan"], kind="scale", replicas=9)
            s["denial"] = Policy.evaluate(alternative, s)
            self.emit("alternative.denied", s["scenario_s"], {"proposal": alternative, **s["denial"]})
            self.save(s)
            return self.state()

    def replay(self):
        with self.lock:
            s = self.load()
            events = self.journal.events(self.run_id)
            recorded_revision = "worker:v1"
            completed = set()
            sample = None
            for e in events:
                p = e["payload"]
                if e["kind"] == "change.recorded":
                    recorded_revision = p["to"]
                elif e["kind"] == "change.applied":
                    recorded_revision = p["revision"]
                elif e["kind"] == "action.completed":
                    completed.add(p["action_id"])
                elif e["kind"] == "telemetry.sample":
                    sample = p
            s["replay"] = {"revision": recorded_revision, "completed_actions": len(completed),
                           "last_queue_age_s": sample["queue_age_s"], "side_effects": 0,
                           "hash_chain_valid": self.journal.verify()["valid"]}
            self.emit("replay.completed", s["scenario_s"], s["replay"])
            self.save(s)
            return self.state()
