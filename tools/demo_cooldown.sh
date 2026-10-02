#!/usr/bin/env bash
# Run this right after a demo/viva to stop paying for a warm GPU container.
# modal_ai.py already has min_containers=0 committed - this just redeploys
# that version so the live service matches the source again.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! grep -q "min_containers=0" modal_ai.py; then
  echo "modal_ai.py does not show min_containers=0 - check the file before deploying." >&2
  exit 1
fi

echo "Redeploying Modal AI service at min_containers=0 (cost-safe idle state)..."
modal deploy modal_ai.py
echo "Done. Container will scale to zero after the normal 5-minute idle window."
