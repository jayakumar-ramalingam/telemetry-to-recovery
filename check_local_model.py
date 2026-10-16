"""Actual Ollama inference integration check. Requires a running local model."""
import json
from pathlib import Path
from ai_investigator import OllamaInvestigator
from engine import RecoveryDemo

root = Path(__file__).resolve().parent
demo = RecoveryDemo(root / "data" / "local-validation.sqlite3", OllamaInvestigator())
results = []
try:
    for scenario in ["memory", "gap"]:
        demo.new_run(scenario)
        for _ in range(3):
            state = demo.next()
        report = state["ai_report"]
        print(json.dumps({"scenario": scenario, "stage": state["stage"], "report": report}), flush=True)
        assert report["model_invoked"] and report["validated"], "No accepted actual model response"
        assert state["stage"] == ("diagnosed" if scenario == "memory" else "stopped")
        if scenario == "memory":
            demo.next()
            demo.approve()
            demo.execute()
            assert demo.verify_recovery()["verification"]["passed"]
            demo.execute()
            assert demo.replay()["replay"]["completed_actions"] == 1
        else:
            assert not state.get("execution")
        results.append({"scenario": scenario, "stage": state["stage"], "report": report,
                        "events": demo.journal.events(demo.run_id)})
    (root / "qa-local").mkdir(exist_ok=True)
    (root / "qa-local" / "actual-model-validation.json").write_text(json.dumps(results, indent=2))
    print("ACTUAL LOCAL MODEL: recovery and evidence-gap checks passed", flush=True)
finally:
    demo.journal.db.close()
