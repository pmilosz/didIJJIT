#!/usr/bin/env bash
# Uruchamia didIJJIT (Linux, macOS, WSL). Pierwsze uruchomienie tworzy .venv i instaluje zależności.
set -e
cd "$(dirname "$0")"
printf '\n  didIJJIT - Did I Just Join IT?\n  ==============================\n\n'
# znacznik powstaje dopiero po udanej instalacji, więc przerwana instalacja zostanie dokończona
if [ ! -f .venv/zainstalowano.txt ]; then
  echo "  Pierwsze uruchomienie - przygotowuję program (zwykle 1-2 minuty)."
  echo
  echo "  [1/2] Tworzę środowisko Pythona..."
  if [ ! -x .venv/bin/python ]; then
    if ! python3 -m venv .venv 2>/dev/null; then
      # Debian/Ubuntu bez pakietu python3-venv: venv bez pipa i pip doinstalowany ręcznie
      rm -rf .venv
      python3 -m venv --without-pip .venv
      curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python - -q
    fi
  fi
  echo "  [2/2] Pobieram biblioteki (poniżej widać postęp)..."
  echo
  .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
  echo ok > .venv/zainstalowano.txt
  printf '\n  Instalacja zakończona.\n\n'
fi
if [ ! -f config.toml ]; then
  cp config.example.toml config.toml
  echo "  Utworzono config.toml - tam wybierzesz kategorie i miasta."
fi
exec .venv/bin/python -m didijjit
