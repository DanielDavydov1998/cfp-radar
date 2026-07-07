@echo off
cd /d "%~dp0"
if not exist .venv (
  echo Erstelle virtuelle Umgebung...
  python -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)
echo.
echo CFP-Radar laeuft auf http://127.0.0.1:8000  (Beenden: Strg+C)
echo.
python app.py
