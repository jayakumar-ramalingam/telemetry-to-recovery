import concurrent.futures
import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import DemoError, Policy, ReasoningAgent, RecoveryDemo


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "events.sqlite3"
        self.demo = RecoveryDemo(self.path)

    def tearDown(self):
        self.demo.journal.db.close()
        self.tmp.cleanup()

    def planned(self):
        for _ in range(4):
            self.demo.next()
        self.assertEqual(self.demo.state()["stage"], "planned")

    def test_full_recovery_and_replay(self):
        self.planned()
        self.demo.approve()
        self.demo.execute()
        state = self.demo.verify_recovery()
        self.assertTrue(state["verification"]["passed"])
        self.assertEqual(state["revision"], "worker:v1")
        replay = self.demo.replay()["replay"]
        self.assertEqual(replay["revision"], state["revision"])
        self.assertEqual(replay["completed_actions"], 1)
        self.assertEqual(replay["side_effects"], 0)
        self.assertTrue(self.demo.journal.verify()["valid"])

    def test_no_approval_no_execution(self):
        self.planned()
        with self.assertRaises(DemoError):
            self.demo.execute()
        self.assertEqual(self.demo.state()["revision"], "worker:v2")

    def test_missing_evidence_escalates(self):
        self.demo.new_run("gap")
        for _ in range(3):
            state = self.demo.next()
        self.assertEqual(state["stage"], "stopped")
        self.assertEqual(state["diagnosis"]["status"], "insufficient_evidence")
        self.assertFalse(any(e["kind"] == "action.started" for e in state["journal"]))

    def test_exact_plan_binding(self):
        self.planned()
        self.demo.approve()
        s = self.demo.load()
        s["plan"]["max_targets"] = 2
        self.demo.save(s)
        with self.assertRaises(DemoError):
            self.demo.execute()

    def test_revision_change_rejected(self):
        self.planned()
        self.demo.approve()
        s = self.demo.load()
        s["revision"] = "worker:v3"
        self.demo.save(s)
        with self.assertRaises(DemoError):
            self.demo.execute()

    def test_stale_evidence_rejected(self):
        self.planned()
        self.demo.approve()
        s = self.demo.load()
        s["scenario_s"] += 31
        self.demo.save(s)
        with self.assertRaises(DemoError):
            self.demo.execute()

    def test_approval_expiry_rejected(self):
        self.planned()
        self.demo.approve()
        s = self.demo.load()
        s["approval"]["at_s"] -= 61
        self.demo.save(s)
        with self.assertRaises(DemoError):
            self.demo.execute()

    def test_duplicate_concurrent_execution(self):
        self.planned()
        self.demo.approve()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.demo.execute(), range(4)))
        events = self.demo.state()["journal"]
        self.assertEqual(sum(e["kind"] == "change.applied" for e in events), 1)
        self.assertEqual(sum(e["kind"] == "action.duplicate_suppressed" for e in events), 3)

    def test_bad_recovery_does_not_report_success(self):
        self.planned()
        self.demo.approve()
        self.demo.execute()
        s = self.demo.verify_recovery(fail=True)
        self.assertFalse(s["verification"]["passed"])
        self.assertEqual(s["stage"], "stopped")

    def test_scale_out_rejected(self):
        self.planned()
        s = self.demo.unsafe_scale()
        self.assertFalse(s["denial"]["allowed"])
        self.assertTrue(any("174%" in c["name"] and not c["passed"] for c in s["denial"]["checks"]))
        self.assertEqual(s["replicas"], 3)

    def test_active_recovery_lock(self):
        self.planned()
        s = self.demo.load()
        s["active_action"] = "another-action"
        self.assertFalse(Policy.evaluate(s["plan"], s)["allowed"])

    def test_compatibility_required(self):
        self.planned()
        s = self.demo.load()
        s["compatible"] = False
        self.assertFalse(Policy.evaluate(s["plan"], s)["allowed"])

    def test_event_rows_append_only(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.demo.journal.db.execute("UPDATE events SET kind='tampered' WHERE seq=1")
        self.demo.journal.db.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            self.demo.journal.db.execute("DELETE FROM events WHERE seq=1")
        self.demo.journal.db.rollback()
        self.assertTrue(self.demo.journal.verify()["valid"])

    def test_restart_resumes_without_reexecuting(self):
        self.planned()
        self.demo.approve()
        self.demo.execute()
        other = RecoveryDemo(self.path)
        self.assertEqual(other.state()["stage"], "executed")
        self.assertEqual(other.run_id, self.demo.run_id)
        other.execute()
        self.assertEqual(sum(e["kind"] == "change.applied" for e in other.state()["journal"]), 1)
        other.journal.db.close()

    def test_agent_ignores_fault_label(self):
        self.demo.next()
        events = [e for e in self.demo.journal.events(self.demo.run_id)
                  if e["kind"] in {"telemetry.sample", "change.recorded", "topology.recorded"}]
        first = ReasoningAgent.run(events)
        modified = copy.deepcopy(events)
        modified.append({"seq": 9999, "kind": "injector.ground_truth", "payload": {"cause": "wrong"}})
        self.assertEqual(first, ReasoningAgent.run(modified))

    def test_traffic_surge_prevents_simple_regression_diagnosis(self):
        self.demo.next()
        events = [e for e in self.demo.journal.events(self.demo.run_id)
                  if e["kind"] in {"telemetry.sample", "change.recorded", "topology.recorded"}]
        for e in events:
            if e["kind"] == "telemetry.sample" and e["payload"]["revision"] == "worker:v2":
                e["payload"]["input_rps"] = 300
        result = ReasoningAgent.run(events)
        self.assertEqual(result["status"], "insufficient_evidence")

    def test_downstream_stop_threshold_enforced_at_execution(self):
        self.planned()
        self.demo.approve()
        s = self.demo.load()
        s["metrics"][-1]["db_pct"] = 90
        self.demo.save(s)
        with self.assertRaises(DemoError):
            self.demo.execute()

    def test_new_run_preserves_previous_history(self):
        old = self.demo.run_id
        count = len(self.demo.journal.events(old))
        self.demo.new_run("gap")
        self.assertNotEqual(self.demo.run_id, old)
        self.assertEqual(len(self.demo.journal.events(old)), count)

    def test_condition_change_preserves_approved_plan_and_original_observation(self):
        self.planned()
        approved = self.demo.approve()
        plan = copy.deepcopy(approved["plan"])
        approval = copy.deepcopy(approved["approval"])
        previous = copy.deepcopy(approved["metrics"][-1])
        s = self.demo.challenge_db_pressure()
        self.assertEqual(s["stage"], "approved")
        self.assertEqual(s["plan"], plan)
        self.assertEqual(s["approval"], approval)
        self.assertEqual(s["metrics"][-2], previous)
        self.assertEqual(s["metrics"][-1]["db_pct"], 90)
        self.assertEqual(s["scenario_s"], approved["scenario_s"] + 5)
        failed = [c["name"] for c in s["execution_policy"]["checks"] if not c["passed"]]
        self.assertEqual(failed, ["Downstream DB remains below the 80% stop threshold"])
        self.assertEqual(s["execution_policy_phase"], "preview")
        self.assertIsNone(s["execution"])
        self.assertTrue(s["integrity"]["valid"])

    def test_changed_conditions_block_execution_and_persist_denial(self):
        self.planned()
        self.demo.approve()
        self.demo.challenge_db_pressure()
        with self.assertRaises(DemoError):
            self.demo.execute()
        s = self.demo.state()
        self.assertEqual(s["stage"], "stopped")
        self.assertTrue(s["execution_blocked"])
        self.assertEqual(s["execution_policy_phase"], "execution")
        self.assertEqual(s["revision"], "worker:v2")
        self.assertIsNone(s["execution"])
        self.assertFalse(any(e["kind"] in {"action.started", "change.applied", "action.completed"} for e in s["journal"]))
        self.assertEqual(sum(e["kind"] == "scenario.condition_changed" for e in s["journal"]), 1)
        self.assertEqual(sum(e["kind"] == "action.denied" for e in s["journal"]), 1)
        restored = RecoveryDemo(self.path)
        try:
            self.assertTrue(restored.state()["execution_blocked"])
            self.assertFalse(restored.state()["execution_policy"]["allowed"])
        finally:
            restored.journal.db.close()

    def test_condition_change_requires_approval_and_is_single_use(self):
        for stage in range(5):
            count = len(self.demo.state()["journal"])
            with self.assertRaises(DemoError):
                self.demo.challenge_db_pressure()
            self.assertEqual(len(self.demo.state()["journal"]), count)
            if stage < 4:
                self.demo.next()
        self.demo.approve()
        self.demo.challenge_db_pressure()
        count = len(self.demo.state()["journal"])
        with self.assertRaises(DemoError):
            self.demo.challenge_db_pressure()
        self.assertEqual(len(self.demo.state()["journal"]), count)

    def test_new_run_clears_condition_change_without_erasing_old_run(self):
        self.planned()
        self.demo.approve()
        self.demo.challenge_db_pressure()
        old_run = self.demo.run_id
        s = self.demo.new_run("memory")
        self.assertIsNone(s["condition_change"])
        self.assertIsNone(s["execution_policy"])
        self.assertFalse(s["execution_blocked"])
        self.assertTrue(any(e["kind"] == "scenario.condition_changed" for e in self.demo.journal.events(old_run)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
