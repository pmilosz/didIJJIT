@echo off
rem Uruchamia didIJJIT w Windows. Pierwsze uruchomienie tworzy .venv i instaluje zależności.
chcp 65001 >nul
rem polskie znaki w komunikatach Pythona niezależnie od ustawień konsoli
set PYTHONUTF8=1
title didIJJIT
cd /d "%~dp0"
echo.
echo   didIJJIT - Did I Just Join IT?
echo   ==============================
echo.

rem znacznik .venv\zainstalowano.txt powstaje dopiero po udanej instalacji,
rem więc przerwana instalacja zostanie dokończona przy następnym starcie
if exist .venv\zainstalowano.txt goto start

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% --version >nul 2>nul || (
  echo   [BŁĄD] Nie znaleziono Pythona. Zainstaluj go z https://www.python.org/downloads/
  echo          i zaznacz przy instalacji "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

echo   Pierwsze uruchomienie - przygotowuję program (zwykle 1-2 minuty).
echo.
echo   [1/2] Tworzę środowisko Pythona...
if not exist .venv\Scripts\python.exe %PY% -m venv .venv || goto blad
echo   [2/2] Pobieram biblioteki (poniżej widać postęp)...
echo.
.venv\Scripts\python -m pip install --disable-pip-version-check --progress-bar on -r requirements.txt || goto blad
echo ok> .venv\zainstalowano.txt
echo.
echo   Instalacja zakończona.
echo.

:start
if not exist config.toml (
  copy config.example.toml config.toml >nul
  echo   Utworzono config.toml - tam wybierzesz kategorie i miasta.
)
.venv\Scripts\python -m didijjit
pause
exit /b 0

:blad
echo.
echo   [BŁĄD] Instalacja się nie udała. Sprawdź połączenie z internetem i uruchom run.bat ponownie.
echo          Jeśli błąd się powtarza, skopiuj komunikat powyżej i zgłoś go na GitHubie (Issues).
echo.
pause
exit /b 1
