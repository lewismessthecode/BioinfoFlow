#!/usr/bin/env bash

set -euo pipefail

uv run pytest \
  tests/test_api/test_runs.py \
  tests/test_api/test_agent_api.py \
  tests/test_api/test_run_wizard.py \
  --cov=app.api.v1.runs \
  --cov=app.api.v1.agent \
  --cov-report=term-missing \
  --cov-fail-under=85
