"""Actual SDK shape validation using Stubber only. No live AWS request."""
import json
import tempfile
import unittest
from pathlib import Path

import boto3
from botocore.stub import Stubber

from ai_investigator import BedrockInvestigator, SCHEMA, SYSTEM, evidence_packet, packed
from engine import RecoveryDemo
from test_ai import FakeConverse


class SDKContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.demo = RecoveryDemo(Path(self.tmp.name) / "test.sqlite3")
        self.demo.next()
        self.packet = evidence_packet(self.demo.journal.events(self.demo.run_id))
        # Explicit dummy credentials prevent SDK credential discovery/network access.
        self.client = boto3.client("bedrock-runtime", region_name="us-east-1",
                                   aws_access_key_id="test-only", aws_secret_access_key="test-only")
        self.params = {"modelId": "test-model", "system": [{"text": SYSTEM}],
                       "messages": [{"role": "user", "content": [{"text": packed({"response_schema": SCHEMA, "input_data": self.packet})}]}],
                       "inferenceConfig": {"maxTokens": 1200, "temperature": 0}}

    def tearDown(self):
        self.demo.journal.db.close()
        self.client.close()
        self.tmp.cleanup()

    def response(self):
        response = FakeConverse().converse(**self.params)
        response["usage"]["totalTokens"] = 520
        response["metrics"] = {"latencyMs": 50}
        return response

    def test_converse_sdk_contract(self):
        with Stubber(self.client) as stub:
            stub.add_response("converse", self.response(), self.params)
            result = BedrockInvestigator("test-model", "us-east-1", client=self.client).investigate(self.packet)
            self.assertTrue(result["validated"])
            self.assertEqual(result["usage"]["totalTokens"], 520)
            stub.assert_no_pending_responses()

    def test_access_denied_is_fail_closed_and_sanitized(self):
        with Stubber(self.client) as stub:
            stub.add_client_error("converse", service_error_code="AccessDeniedException",
                                  service_message="Private account/profile details", expected_params=self.params)
            result = BedrockInvestigator("test-model", "us-east-1", client=self.client).investigate(self.packet)
            self.assertFalse(result["validated"])
            self.assertNotIn("Private account", result["error"])
            self.assertIn("AccessDeniedException", result["error"])

    def test_malformed_json_rejected(self):
        response = self.response()
        response["output"]["message"]["content"] = [{"text": "not JSON"}]
        with Stubber(self.client) as stub:
            stub.add_response("converse", response, self.params)
            result = BedrockInvestigator("test-model", "us-east-1", client=self.client).investigate(self.packet)
            self.assertEqual(result["status"], "rejected")
            self.assertTrue(result["model_invoked"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
