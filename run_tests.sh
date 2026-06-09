#!/usr/bin/env bash
set -euo pipefail

cmd=(python -m pytest test/)

if [[ "${AUDIOPIPE_INTEGRATION:-0}" == "1" ]]; then
  cmd+=(--integration)
fi

if [[ "${AUDIOPIPE_SLOW:-0}" == "1" ]]; then
  cmd+=(--runslow)
fi

"${cmd[@]}" "$@"
