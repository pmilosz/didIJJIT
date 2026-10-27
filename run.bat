@echo off
rem Uruchamia didIJJIT w Windows. Pierwsze uruchomienie tworzy .venv i instaluje zaleznosci.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install -q -r requirements.txt
)
if not exist config.toml copy config.example.toml config.toml >nul
.venv\Scripts\python -m didijjit
pause
