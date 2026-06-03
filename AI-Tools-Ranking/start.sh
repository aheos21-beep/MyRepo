#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
pip install -q -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
