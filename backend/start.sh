#!/bin/sh
set -eu

alembic upgrade head

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  python seed.py
elif [ "${SEED_DEMO_DATA:-false}" = "if-empty" ]; then
  python bootstrap_demo.py
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
