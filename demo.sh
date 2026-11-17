#!/usr/bin/env bash
# PermaInfer demo — end to end, no accounts, no payment.
#
# 1. Starts the server (echo backend if no model file is present,
#    real llama.cpp backend otherwise).
# 2. Sends a chat completion, prints the response + its receipt id.
# 3. Fetches the receipt, verifies the ledger chain, and prints the
#    exact Arweave payload that would anchor the receipt permanently.
#
# Usage:  ./demo.sh            (uses models/qwen2.5-0.5b-instruct-q4_k_m.gguf if present)
#         PERMAINFER_BACKEND=echo ./demo.sh   (no model needed)
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PERMAINFER_PORT:-8000}"
LEDGER="${PERMAINFER_LEDGER:-data/demo-ledger.jsonl}"
PYTHON="${PYTHON:-.venv/bin/python}"
export PERMAINFER_LEDGER="$LEDGER"
export PERMAINFER_NO_AUTOSTART=1
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -f "models/qwen2.5-0.5b-instruct-q4_k_m.gguf" ]; then
  echo "No model file found — demo runs with the echo backend (receipts still real)."
  export PERMAINFER_BACKEND=echo
fi

# Fresh demo ledger so the chain starts at genesis.
rm -f "$LEDGER"

echo "== starting server on :$PORT =="
$PYTHON -m permainfer.cli serve --port "$PORT" > /tmp/permainfer-demo.log 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT

for _ in $(seq 1 180); do
  if curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1; then break; fi
  sleep 1
done

echo
echo "== /health =="
curl -s "http://localhost:$PORT/health"; echo

echo
echo "== chat completion =="
RESP=$(curl -s -X POST "http://localhost:$PORT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen2.5-0.5B-Instruct-GGUF","messages":[{"role":"user","content":"In one sentence, why should AI infrastructure be decentralized?"}]}')
echo "$RESP" | $PYTHON -m json.tool
RECEIPT_ID=$(echo "$RESP" | $PYTHON -c "import json,sys; print(json.load(sys.stdin)['permainfer_receipt']['receipt_id'])")

echo
echo "== receipt $RECEIPT_ID =="
curl -s "http://localhost:$PORT/receipts/$RECEIPT_ID" | $PYTHON -m json.tool

echo
echo "== ledger verify =="
$PYTHON -m permainfer.cli verify --ledger "$LEDGER"

echo
echo "== Arweave payload for this receipt (dry run — nothing uploaded) =="
$PYTHON -m permainfer.cli arweave-payload --ledger "$LEDGER" --receipt "$RECEIPT_ID" \
  | $PYTHON -c "import json,sys; p=json.load(sys.stdin); print('tags:', [t['name']+'='+t['value'][:40] for t in p['tags']]); print('data bytes:', len(p['data_json']))"

echo
echo "Demo done. Ledger: $LEDGER"
