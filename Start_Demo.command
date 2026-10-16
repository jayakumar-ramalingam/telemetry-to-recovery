#!/bin/sh
# Launches Ollama if needed, then the local teaching server. Stop server with Control-C.
cd -- "$(dirname -- "$0")" || exit 1
if ! curl --silent --fail --max-time 2 http://127.0.0.1:11434/api/version >/dev/null; then
  if [ -x .build/ollama/ollama ]; then
    demo_ollama_bin="$PWD/.build/ollama/ollama"
  elif command -v ollama >/dev/null 2>&1; then
    demo_ollama_bin="$(command -v ollama)"
  else
    echo "Install Ollama and pull llama3.1:8b first. See LOCAL_SETUP.md."
    exit 1
  fi
  mkdir -p data
  OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS="$PWD/data/ollama-models" \
    "$demo_ollama_bin" serve >data/ollama-server.log 2>&1 &
  echo "Started local Ollama (PID $!). Cloud disabled."
  sleep 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.10 or later is required. See README.md."
  exit 1
fi
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python server.py --provider ollama --port 8768 --db data/recording-local.sqlite3
fi
exec python3 server.py --provider ollama --port 8768 --db data/recording-local.sqlite3
