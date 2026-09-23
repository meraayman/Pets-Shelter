@echo off
REM Double-click this file to start the Pet Adoption System on Windows.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo First run: setting things up. This takes about a minute...
    python -m venv .venv || (echo Python is not installed. Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH". & pause & exit /b 1)
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || (echo Could not install the requirements. Check your internet connection. & pause & exit /b 1)
)
".venv\Scripts\python.exe" app.py %*
pause
