"""Start: python -m didijjit (port z config.toml)."""
import itertools
import os
import platform
import socket
import sys
import threading
import time
import webbrowser

from . import config


def _ready(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _announce(port: int) -> None:
    """Kręciołek do czasu, aż serwer odpowie; potem adres i otwarcie przeglądarki."""
    url = f"http://localhost:{port}"
    spinner = itertools.cycle("|/-\\")
    deadline = time.time() + 60
    while not _ready(port):
        if time.time() > deadline:
            print("\r  Serwer nie wystartował w ciągu minuty — sprawdź komunikaty powyżej.")
            return
        sys.stdout.write(f"\r  Uruchamiam serwer {next(spinner)} ")
        sys.stdout.flush()
        time.sleep(0.15)
    print(f"\r  Gotowe! didIJJIT działa: {url}       ", flush=True)
    print("  Zostaw to okno otwarte. Zamknięcie okna (albo Ctrl+C) wyłącza program.\n", flush=True)
    # bez środowiska graficznego Linux otworzyłby przeglądarkę tekstową w terminalu
    if platform.system() != "Linux" or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        webbrowser.open(url)


if __name__ == "__main__":
    port = config.load().port
    if _ready(port):
        print(f"  Port {port} jest zajęty — didIJJIT już działa? Otwórz http://localhost:{port}")
        print("  Jeśli to inny program, zmień port w config.toml ([server] port).")
        sys.exit(1)
    threading.Thread(target=_announce, args=(port,), daemon=True).start()
    import uvicorn  # import po starcie kręciołka — pierwszy import w Windows potrafi trwać kilka sekund

    uvicorn.run("didijjit.app:app", host="127.0.0.1", port=port, log_level="warning")
