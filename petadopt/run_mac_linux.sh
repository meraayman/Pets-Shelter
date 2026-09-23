#!/usr/bin/env bash
# Start the Pet Adoption System on macOS or Linux:  ./run_mac_linux.sh
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "First run: setting things up. This takes about a minute..."
  python3 -m venv .venv || { echo "Python 3 is not installed. Get it from https://www.python.org/downloads/"; exit 1; }
  .venv/bin/python -m pip install --quiet -r requirements.txt || { echo "Could not install the requirements. Check your internet connection."; exit 1; }
fi
exec .venv/bin/python app.py "$@"
