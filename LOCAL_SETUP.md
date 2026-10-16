# Local Llama setup

The local provider uses **Llama 3.1 8B through Ollama**. No AWS account or API key is required. The workload and actuator remain synthetic; the investigator response is actual model inference.

## Install and download before presenting

Requires Python 3.10 or later and a local Ollama installation from [ollama.com](https://ollama.com/). Allow approximately 5 GB of disk space for the selected model and sufficient memory for inference; the original rehearsal used a 24 GB Apple Silicon Mac. Performance on other machines must be rehearsed, not assumed.

From the repository folder, start a demo-owned daemon in one terminal:

```sh
OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS="$PWD/data/ollama-models" ollama serve
```

If a daemon is already using this port, do not launch another over it. Check how that daemon is configured first. Use the same model storage configuration for download and inference.

In a second terminal:

```sh
ollama pull llama3.1:8b
python3 server.py --provider ollama --port 8768
```

Open **http://127.0.0.1:8768**. The initial installation and model pull need internet. Once the runtime and model are installed locally, the lab does not require venue internet. The adapter accepts only loopback model endpoints, bypasses HTTP proxies, rejects redirects and cloud model tags, and supplies no execution tools. Keep the daemon's cloud features disabled as well.

The source repository does not include a model, runtime, database, recording, or Python virtual environment. Download dependencies separately on each presentation machine.

## Optional macOS launcher

After installing Ollama and downloading the model into the demo-owned directory, double-click `Start_Demo.command` or run:

```sh
sh Start_Demo.command
```

It starts a local daemon if absent and uses port 8768 for the teaching server. If a compatible daemon or demo server is already running, use the existing service rather than launching duplicates. Control-C stops the web server, not a separately running model daemon. If the model is unavailable, investigation stops rather than fabricating a response.

## Preflight

Run the offline tests:

```sh
python3 -m unittest -v test_engine.py test_ai.py test_ollama.py
```

With the local model daemon running, exercise actual inference separately:

```sh
python3 check_local_model.py
```

This makes two inference calls and generates local evidence in `data/` and `qa-local/`. Passing means the supported and missing-evidence scenarios exercised their expected control paths. It does not establish the truth of every model sentence or general diagnostic accuracy. Rehearse on the presentation laptop after changing models or runtime versions.

## Live presentation

Follow [LIVE_DEMO.md](LIVE_DEMO.md). Start the daemon in advance and rehearse a full investigation so initial model loading does not surprise you on stage. Show the actual response, even if it refuses. A failed or invalid response must not be bypassed to produce a successful-looking recovery.

For optional browser recording:

```sh
DEMO_URL=http://127.0.0.1:8768 DEMO_RECORD_DIR=recordings-local node record_demo.mjs
```

Recording requires Playwright, an installed compatible browser, and FFmpeg. The recording is silent for live narration and is generated locally, not included in Git.

## Stop

Control-C stops the server. If you started `ollama serve` in its own terminal, Control-C there stops that daemon. To unload the model without deleting its downloaded files:

```sh
ollama stop llama3.1:8b
```

The explicit alternative is `python3 server.py --provider rules`. Describe it as rules-only, not model inference. Optional cloud-provider setup is in [BEDROCK_SETUP.md](BEDROCK_SETUP.md).
