"""Offline adapter contract tests. These test doubles are not model inference."""
import tempfile
import unittest
from pathlib import Path

from ai_investigator import OllamaInvestigator
from engine import RecoveryDemo
from test_ai import FakeConverse


class FakeOllama:
    def __init__(self, mutate=None):
        self.requests = []
        self.mutate = mutate

    def __call__(self, body):
        self.requests.append(body)
        converse = FakeConverse().converse(messages=[{"content": [{"text": body["messages"][1]["content"]}]}])
        response = {"done": True, "done_reason": "stop", "message": {"role": "assistant", "content":
                    converse["output"]["message"]["content"][0]["text"]}, "prompt_eval_count": 400, "eval_count": 120}
        if self.mutate:
            self.mutate(response)
        return response


class OllamaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake = FakeOllama()
        self.investigator = OllamaInvestigator(transport=self.fake)
        self.demo = RecoveryDemo(Path(self.tmp.name) / "events.sqlite3", self.investigator)

    def tearDown(self):
        self.demo.journal.db.close()
        self.tmp.cleanup()

    def diagnose(self):
        for _ in range(3):
            state = self.demo.next()
        return state

    def test_schema_request_no_tools_and_validated_response(self):
        state = self.diagnose()
        self.assertEqual(state["stage"], "diagnosed")
        self.assertTrue(state["ai_report"]["validated"])
        request = self.fake.requests[0]
        self.assertEqual(request["model"], "llama3.1:8b")
        self.assertFalse(request["stream"])
        self.assertEqual(request["format"]["type"], "object")
        self.assertNotIn("tools", request)
        self.demo.next()
        self.demo.approve()
        self.demo.execute()
        self.assertTrue(self.demo.verify_recovery()["verification"]["passed"])

    def test_missing_evidence_escalates(self):
        self.demo.new_run("gap")
        state = self.diagnose()
        self.assertTrue(state["ai_report"]["validated"])
        self.assertEqual(state["stage"], "stopped")
        self.assertFalse(state.get("execution"))

    def test_summary_is_measured_and_change_citations_remain_distinct(self):
        state = self.diagnose()
        packet = state["ai_packet"]
        readings = packet["observation_summary"]["by_revision"]
        self.assertEqual(readings["worker:v2"]["db_pct"]["max"], 58)
        self.assertEqual(readings["worker:v2"]["memory_mb"]["max"], 490)
        self.assertEqual(readings["worker:v1"]["memory_mb"]["max"], 122)
        self.assertTrue(packet["citation_index"]["change.recorded"])
        self.assertTrue(set(packet["citation_index"]["change.recorded"]).isdisjoint(packet["citation_index"]["telemetry.sample"]))

    def test_truncated_response_rejected(self):
        self.fake.mutate = lambda r: r.update(done_reason="length")
        state = self.diagnose()
        self.assertEqual(state["stage"], "stopped")
        self.assertTrue(state["ai_report"]["model_invoked"])
        self.assertFalse(state["ai_report"]["validated"])

    def test_tools_rejected(self):
        self.fake.mutate = lambda r: r["message"].update(tool_calls=[{"name": "shell"}])
        self.assertEqual(self.diagnose()["ai_report"]["status"], "rejected")

    def test_no_server_fails_closed(self):
        def unavailable(body):
            raise ConnectionRefusedError()
        self.investigator._transport = unavailable
        state = self.diagnose()
        self.assertEqual(state["stage"], "stopped")
        self.assertFalse(state["ai_report"]["model_invoked"])
        self.assertTrue(state["ai_report"]["request_attempted"])

    def test_remote_urls_and_cloud_models_disallowed(self):
        for url in ["https://example.com", "http://0.0.0.0:11434", "http://127.0.0.1:11434/path", "http://u:p@127.0.0.1:11434"]:
            with self.assertRaises(ValueError):
                OllamaInvestigator(base_url=url)
        for model in ["llama:cloud", "https://registry/model", "remote/model:8b"]:
            with self.assertRaises(ValueError):
                OllamaInvestigator(model_id=model)


if __name__ == "__main__":
    unittest.main()
