#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# This preset uses the recorded real Binance capture, not a current quotation.
export MIE_REPLAY_SNAPSHOT="$PROJECT_DIR/examples/task03-btc-snapshot.json"
export MIE_MODEL_BUNDLE="$PROJECT_DIR/examples/task03-btc-model.json"
export MIE_PREDICTION_DATASET="$PROJECT_DIR/examples/task03-btc-dataset.json"
exec bash "$PROJECT_DIR/scripts/start-web.sh"
