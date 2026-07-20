#!/usr/bin/env bash
# Compile and run the pure billing-core unit tests in plain Node (no jest/expo needed).
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="$(mktemp -d)"
npx tsc src/services/billingCore.ts src/services/billingCore.test.ts \
  --outDir "$OUT" --module commonjs --target es2019 --esModuleInterop --skipLibCheck --moduleResolution node
node "$OUT/billingCore.test.js"
