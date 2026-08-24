#!/bin/sh
export PYTHONPATH=/app
exec python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
