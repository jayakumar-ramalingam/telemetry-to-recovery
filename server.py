#!/usr/bin/env python3
"""Run locally: python3 server.py. No third-party Python packages required."""
import argparse
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from engine import DemoError, RecoveryDemo
from ai_investigator import BedrockInvestigator, OllamaInvestigator

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "incidents.sqlite3")
    parser.add_argument("--provider", choices=["ollama", "bedrock", "rules"], default="ollama")
    parser.add_argument("--model-id", default=None)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "")))
    parser.add_argument("--profile", default=None, help="Local AWS profile name; never sent to the browser")
    args = parser.parse_args()
    investigator = None
    if args.provider == "ollama":
        investigator = OllamaInvestigator(args.model_id or "llama3.1:8b", args.ollama_url)
    elif args.provider == "bedrock":
        investigator = BedrockInvestigator(args.model_id or os.environ.get("DEMO_BEDROCK_MODEL_ID", ""), args.region, args.profile)
    demo = RecoveryDemo(args.db, investigator=investigator)
    token = secrets.token_urlsafe(24)

    class Handler(BaseHTTPRequestHandler):
        def respond(self, body, content_type="application/json", status=200):
            body = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            route = urlparse(self.path).path
            if route == "/api/state":
                with demo.lock:
                    return self.respond(demo.state())
            if route == "/api/export":
                with demo.lock:
                    return self.respond({"disclosure": "Synthetic workload and actuator, optional read-only model investigation; not the evaluated research prototype", "events": demo.journal.events(demo.run_id), "integrity": demo.journal.verify()})
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if route in assets:
                name, mime = assets[route]
                data = (ROOT / "web" / name).read_bytes()
                if name == "index.html":
                    data = data.replace(b"__DEMO_TOKEN__", token.encode())
                return self.respond(data, mime)
            return self.respond({"error": "Not found"}, status=404)

        def do_POST(self):
            origin = self.headers.get("Origin")
            expected = f"http://127.0.0.1:{args.port}"
            if self.headers.get("X-Demo-Token") != token or (origin and origin != expected):
                return self.respond({"error": "Local demo token or origin mismatch"}, status=403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 4096:
                    raise DemoError("Request too large")
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise DemoError("Request must be a JSON object")
                with demo.lock:
                    if self.path != "/api/new" and body.get("run_id") != demo.run_id:
                        raise DemoError("This browser has an old run. Refresh before acting.")
                    actions = {"/api/next": demo.next, "/api/approve": demo.approve,
                               "/api/execute": demo.execute, "/api/verify": demo.verify_recovery,
                               "/api/unsafe-scale": demo.unsafe_scale, "/api/replay": demo.replay,
                               "/api/challenge-db": demo.challenge_db_pressure}
                    if self.path == "/api/new":
                        result = demo.new_run(body.get("scenario", "memory"))
                    elif self.path in actions:
                        result = actions[self.path]()
                    else:
                        return self.respond({"error": "Not found"}, status=404)
                    return self.respond(result)
            except DemoError as exc:
                with demo.lock:
                    return self.respond({"error": str(exc), "state": demo.state()}, status=409)
            except (ValueError, TypeError) as exc:
                return self.respond({"error": str(exc)}, status=409)

        def log_message(self, fmt, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Demo ready: http://127.0.0.1:{args.port}", flush=True)
    print(f"Loopback only. Synthetic workload and actuator. Investigator: {args.provider}.", flush=True)
    if investigator:
        print("Model mode: one bounded inference request per investigation; no infrastructure-write tools.", flush=True)
        if args.provider == "bedrock" and not investigator.public_config()["configured"]:
            print("Bedrock model/region not configured. Investigation will fail closed. See BEDROCK_SETUP.md.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
