#!/usr/bin/env bash
set -euo pipefail

USE_DOPPLER="${USE_DOPPLER_ON_RENDER:-false}"
USE_DOPPLER="$(echo "$USE_DOPPLER" | tr '[:upper:]' '[:lower:]')"

APP_CMD=(uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}")

if [[ "$USE_DOPPLER" != "true" && "$USE_DOPPLER" != "1" && "$USE_DOPPLER" != "yes" ]]; then
  exec "${APP_CMD[@]}"
fi

if [[ -z "${DOPPLER_TOKEN:-}" ]]; then
  echo "USE_DOPPLER_ON_RENDER is enabled but DOPPLER_TOKEN is missing." >&2
  exit 1
fi

if [[ -z "${DOPPLER_PROJECT:-}" || -z "${DOPPLER_CONFIG:-}" ]]; then
  echo "USE_DOPPLER_ON_RENDER is enabled but DOPPLER_PROJECT or DOPPLER_CONFIG is missing." >&2
  exit 1
fi

if ! command -v doppler >/dev/null 2>&1; then
  echo "Doppler CLI not found. Installing..." >&2
  curl -Ls https://cli.doppler.com/install.sh | sh
  export PATH="$HOME/.doppler/bin:$PATH"
fi

exec doppler run --project "$DOPPLER_PROJECT" --config "$DOPPLER_CONFIG" -- "${APP_CMD[@]}"
