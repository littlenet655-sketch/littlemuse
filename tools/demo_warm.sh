#!/usr/bin/env bash
# Run this ~15-20 minutes before a demo/viva so the Modal GPU container
# is already warm when the professor uploads the first photo/video.
#
# What it does: temporarily sets min_containers=1 on the ai_web function
# in modal_ai.py, redeploys, then restores the file to min_containers=0
# so your source tree is never left in the "always pay" state.
#
# Cost note: a warm T4 costs money for every minute it's up. Run
# demo_cooldown.sh right after you're done presenting.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! grep -q "min_containers=0" modal_ai.py; then
  echo "min_containers=0 not found in modal_ai.py - check the file wasn't already changed." >&2
  exit 1
fi

sed -i.bak 's/min_containers=0,/min_containers=1,/' modal_ai.py
echo "Deploying warm Modal AI service (min_containers=1)..."
modal deploy modal_ai.py
mv modal_ai.py.bak modal_ai.py
echo "Done. Source restored to min_containers=0. The deployed container stays warm until you run demo_cooldown.sh."
