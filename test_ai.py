"""Contract tests use explicit test doubles; no model/cloud calls are made."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from ai_investigator import BedrockInvestigator, ModelOutputError, evidence_packet, validate_output
from engine import DemoError, RecoveryDemo


class FakeConverse:
    def __init__(self, mutate=None, error=None):
        self.mutate = mutate
        self.error = error
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        packet = json.loads(kwargs["messages"][0]["content"][0]["text"])["input_data"]
        obs = packet["observations"]
        sample = [e for e in obs if e["kind"] == "telemetry.sample"]
        change = [e for e in obs if e["kind"] == "change.recorded"][-1]
        missing = not sample[-1]["payload"]["memory_observed"]
        analysis = {"summary": "Worker v2 is a regression hypothesis; a bounded rollback trial is proposed." if not missing else "Memory observations are missing; investigate before acting.",
                    "status": "supported_hypothesis" if not missing else "insufficient_evidence",
                    "hypotheses": [{"name": "Worker regression", "verdict": "supported" if not missing else "unresolved", "why": "Compare the release and recorded observations."}],
                    "evidence": [sample[0]["seq"], change["seq"], sample[-1]["seq"]],
                    "runbook_refs": ["rb-workers-memory@1.0"], "unknowns": ["Exact code defect is not established."],
                    "proposed_action": "rollback" if not missing else "escalate", "target": "demo/workers"}
        if self.mutate:
            self.mutate(analysis)
        return {"stopReason": "end_turn", "output": {"message": {"role": "assistant", "content": [{"text": json.dumps(analysis)}]}},
                "usage": {"inputTokens": 400, "outputTokens": 120}}


class BedrockContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "incident.sqlite3"
        self.fake = FakeConverse()
        self.investigator = BedrockInvestigator("test-model", "test-region", client=self.fake)
        self.demo = RecoveryDemo(self.path, self.investigator)

    def tearDown(self):
        self.demo.journal.db.close()
        self.tmp.cleanup()

    def diagnose(self):
        for _ in range(3):
            state = self.demo.next()
        return state

    def test_valid_model_proposal_requires_independent_checks_and_approval(self):
        s = self.diagnose()
        self.assertEqual(s["stage"], "diagnosed")
        self.assertTrue(s["ai_report"]["validated"])
        self.assertTrue(s["ai_report"]["model_invoked"])
        self.assertEqual(len(self.fake.calls), 1)
        self.demo.next()
        with self.assertRaises(DemoError):
            self.demo.execute()
        self.demo.approve()
        self.demo.execute()
        self.assertTrue(self.demo.verify_recovery()["verification"]["passed"])

    def test_late_db_change_keeps_model_context_and_approval_but_blocks_execution(self):
        diagnosed = self.diagnose()
        packet = copy.deepcopy(diagnosed["ai_packet"])
        report = copy.deepcopy(diagnosed["ai_report"])
        self.demo.next()
        approved = self.demo.approve()
        changed = self.demo.challenge_db_pressure()
        self.assertEqual(changed["ai_packet"], packet)
        self.assertEqual(changed["ai_report"], report)
        self.assertEqual(changed["plan"], approved["plan"])
        self.assertEqual(changed["approval"], approved["approval"])
        self.assertEqual(len(self.fake.calls), 1)
        with self.assertRaises(DemoError):
            self.demo.execute()
        self.assertTrue(self.demo.state()["execution_blocked"])
        self.assertFalse(any(e["kind"] == "change.applied" for e in self.demo.state()["journal"]))

    def test_prompt_has_separate_roles_and_no_tools_or_injector_labels(self):
        self.diagnose()
        request = self.fake.calls[0]
        self.assertNotIn("toolConfig", request)
        self.assertIn("read-only", request["system"][0]["text"])
        data = json.loads(request["messages"][0]["content"][0]["text"])["input_data"]
        self.assertTrue(data["runbooks"])
        self.assertTrue(all(e["kind"] in {"telemetry.sample", "change.recorded", "topology.recorded"} for e in data["observations"]))
        self.assertNotIn("run.started", json.dumps(data))
        self.assertNotIn("test-profile-secret", json.dumps(request))

    def test_unknown_evidence_id_rejected(self):
        self.fake.mutate = lambda a: a.update(evidence=[999999])
        s = self.diagnose()
        self.assertEqual(s["stage"], "stopped")
        self.assertFalse(s["ai_report"]["validated"])

    def test_unknown_runbook_rejected(self):
        self.fake.mutate = lambda a: a.update(runbook_refs=["invented-runbook"])
        self.assertEqual(self.diagnose()["stage"], "stopped")

    def test_arbitrary_action_rejected(self):
        self.fake.mutate = lambda a: a.update(proposed_action="delete_database")
        self.assertEqual(self.diagnose()["stage"], "stopped")

    def test_other_target_rejected(self):
        self.fake.mutate = lambda a: a.update(target="production/payments")
        self.assertEqual(self.diagnose()["stage"], "stopped")

    def test_extra_command_or_approval_fields_rejected(self):
        self.fake.mutate = lambda a: a.update(command="kubectl delete", approved=True)
        s = self.diagnose()
        self.assertEqual(s["stage"], "stopped")
        self.assertIsNone(s["approval"])
        self.assertIsNone(s["execution"])

    def test_missing_unknowns_rejected(self):
        self.fake.mutate = lambda a: a.update(unknowns=[])
        self.assertEqual(self.diagnose()["stage"], "stopped")

    def test_unavailable_model_does_not_fall_back_to_execution(self):
        self.fake.error = TimeoutError("private SDK details should not be shown")
        s = self.diagnose()
        self.assertEqual(s["stage"], "stopped")
        self.assertEqual(s["rule_diagnosis"]["status"], "supported_hypothesis")
        self.assertFalse(s["ai_report"]["validated"])
        self.assertNotIn("private SDK details", s["ai_report"]["error"])
        self.assertTrue(s["ai_report"]["request_attempted"])
        self.assertEqual(len(self.fake.calls), 1)

    def test_missing_configuration_stops_without_invocation(self):
        self.demo.investigator = BedrockInvestigator()
        s = self.diagnose()
        self.assertEqual(s["stage"], "stopped")
        self.assertFalse(s["ai_report"]["request_attempted"])
        self.assertFalse(s["ai_report"]["model_invoked"])

    def test_missing_evidence_still_blocks_valid_but_wrong_model_recommendation(self):
        self.demo.new_run("gap")
        self.fake.mutate = lambda a: a.update(status="supported_hypothesis", proposed_action="rollback")
        s = self.diagnose()
        self.assertTrue(s["ai_report"]["validated"])
        self.assertEqual(s["stage"], "stopped")
        self.assertEqual(s["rule_diagnosis"]["status"], "insufficient_evidence")

    def test_valid_model_escalation_blocks_even_if_rules_would_allow(self):
        self.fake.mutate = lambda a: a.update(status="insufficient_evidence", proposed_action="escalate")
        s = self.diagnose()
        self.assertEqual(s["rule_diagnosis"]["status"], "supported_hypothesis")
        self.assertEqual(s["stage"], "stopped")

    def test_reference_check_does_not_accept_bools_as_event_ids(self):
        self.fake.mutate = lambda a: a.update(evidence=[True])
        self.assertEqual(self.diagnose()["stage"], "stopped")

    def test_response_and_request_are_recorded(self):
        s = self.diagnose()
        kinds = [e["kind"] for e in s["journal"]]
        self.assertIn("agent.ai_request", kinds)
        self.assertIn("agent.ai_response", kinds)
        self.assertIn("runbooks.retrieved", kinds)
        self.assertEqual(len(s["ai_report"]["response_sha256"]), 64)
        self.assertEqual(len(s["ai_report"]["input_sha256"]), 64)

    def test_unvalidated_model_cannot_be_bypassed_by_stamped_diagnosis(self):
        self.diagnose()
        self.demo.next()
        s = self.demo.load()
        s["ai_report"]["validated"] = False
        self.demo.save(s)
        with self.assertRaises(DemoError):
            self.demo.approve()

    def test_retrieval_is_versioned_and_service_scoped(self):
        self.demo.next()
        packet = evidence_packet(self.demo.journal.events(self.demo.run_id))
        self.assertEqual(packet["scope"], "demo/workers")
        self.assertTrue(all(b["service"] == "demo/workers" for b in packet["runbooks"]))
        self.assertTrue(all(len(b["content_sha256"]) == 64 for b in packet["runbooks"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
