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


if __name__ == "__main__":
    unittest.main(verbosity=2)
