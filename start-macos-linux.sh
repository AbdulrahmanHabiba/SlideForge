#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
printf '\nOpen http://127.0.0.1:8000 in your browser\n'
python run.py
