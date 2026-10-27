"""Start: python -m didijjit (port z config.toml)."""
import os
import platform
import webbrowser

import uvicorn

from . import config

if __name__ == "__main__":
    port = config.load().port
    print(f"didIJJIT działa: http://localhost:{port}  (zatrzymanie: Ctrl+C)")
    # bez środowiska graficznego Linux otworzyłby przeglądarkę tekstową w terminalu
    if platform.system() != "Linux" or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        webbrowser.open(f"http://localhost:{port}")
    uvicorn.run("didijjit.app:app", host="127.0.0.1", port=port, log_level="warning")
