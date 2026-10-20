#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== 1/8: Python syntax ==="
python -m py_compile \
  agent.py dashboard.py queue_store.py quality_outputs.py \
  bridge/bridge.py \
  agents/dispatch.py agents/adhd_style.py agents/orchestrate.py agents/practice.py \
  video_studio/studio.py video_studio/production.py video_studio/research.py \
  video_studio/validate_render.py video_studio/validate_frames.py \
  video_studio/release_gate.py video_studio/publish_youtube.py \
  product_studio/build_product.py

echo "=== 2/8: JavaScript and JSON contracts ==="
node --check video_studio/render.js
python -m json.tool video_studio/storyboard.example.json > /dev/null
python -m json.tool agents/roster.json > /dev/null
python -m json.tool agents/skillbooks.json > /dev/null

echo "=== 3/8: Product builder smoke test ==="
python product_studio/build_product.py \
  --title "Render CI Utility" \
  --idea "Synthetic CI product-builder smoke test" \
  --out workspace/render-ci-product

echo "=== 4/8: Complete Python unit-test suite ==="
python -m unittest discover -s tests -v

echo "=== 5/8: Install and audit video-render dependencies ==="
npm --prefix video_studio install --no-audit --no-fund
npm --prefix video_studio audit --audit-level=high

echo "=== 6/8: Confirm unsafe storyboards are rejected before rendering ==="
set +e
(cd video_studio && node render.js storyboard.invalid-transition.json > /tmp/render-invalid-transition.log 2>&1)
invalid_code=$?
set -e
if [ "$invalid_code" -eq 0 ]; then
  echo "ERROR: invalid transition was unexpectedly accepted"
  cat /tmp/render-invalid-transition.log
  exit 1
fi
grep -q "Unsupported transition_in" /tmp/render-invalid-transition.log || {
  cat /tmp/render-invalid-transition.log
  echo "ERROR: invalid-transition test failed for an unexpected reason"
  exit 1
}

set +e
(cd video_studio && node render.js storyboard.over-limit.json > /tmp/render-over-limit.log 2>&1)
limit_code=$?
set -e
if [ "$limit_code" -eq 0 ]; then
  echo "ERROR: oversized storyboard was unexpectedly accepted"
  cat /tmp/render-over-limit.log
  exit 1
fi
grep -q "30000-frame render limit" /tmp/render-over-limit.log || {
  cat /tmp/render-over-limit.log
  echo "ERROR: frame-limit test failed for an unexpected reason"
  exit 1
}

echo "=== 7/8: CEO queue -> delegated agents -> generated package -> MP4 ==="
python ci/render/e2e_smoke.py

echo "=== 8/8: Landscape and vertical Shorts MP4 validation ==="
python video_studio/studio.py \
  --storyboard video_studio/storyboard.smoke.json \
  --output workspace/render-ci-landscape.mp4
python video_studio/studio.py \
  --storyboard video_studio/storyboard.smoke-shorts.json \
  --output workspace/render-ci-shorts.mp4

echo "PASS: all Render test phases completed"
