#!/usr/bin/env bash
# Uruchamia didIJJIT (Linux, macOS, WSL). Pierwsze uruchomienie tworzy .venv i instaluje zależności.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c "import uvicorn" 2>/dev/null; then
  rm -rf .venv
  if ! python3 -m venv .venv 2>/dev/null; then
    # Debian/Ubuntu bez pakietu python3-venv: venv bez pipa i pip doinstalowany ręcznie
    python3 -m venv --without-pip .venv
    curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python - -q
  fi
  .venv/bin/python -m pip install -q -r requirements.txt
fi
[ -f config.toml ] || cp config.example.toml config.toml
exec .venv/bin/python -m didijjit
