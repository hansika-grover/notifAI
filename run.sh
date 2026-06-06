#!/usr/bin/env bash
set -e
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q -r requirements.txt
echo "Starting Signal Room on http://127.0.0.1:8000  (Ctrl+C to stop)"
python app.py
