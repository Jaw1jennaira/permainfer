# PermaInfer on Nosana — deployment notes
#
# This folder contains the exact job definition used to run PermaInfer on
# Nosana's decentralized GPU network. Nothing here costs anything to
# read or review; actually launching it spends Nosana credits
# (the hackathon gives the first 500 eligible participants $70 each —
# claim them at https://decentralizeai.tech — a user step, see
# SUBMISSION.md).
#
# ---------------------------------------------------------------------------
# What the job does
# ---------------------------------------------------------------------------
# - Pulls ghcr.io/YUSMARA/permainfer:0.1.0 (built from the Dockerfile in
#   this repo, model weights baked in — no download at runtime).
# - Runs the FastAPI inference server on port 8000 (exposed via Nosana).
# - Writes every inference receipt to data/ledger.jsonl inside the job.
# - 1 replica, Simple strategy, 6-hour container timeout (NOT Infinite —
#   see the hackathon announcement: Infinite burns credits 24/7).
#
# ---------------------------------------------------------------------------
# How to deploy (user step — needs a Nosana account + claimed credits)
# ---------------------------------------------------------------------------
# 1. Build + push the image (once, from the repo root):
#        docker build -t ghcr.io/YUSMARA/permainfer:0.1.0 .
#        docker push ghcr.io/YUSMARA/permainfer:0.1.0
#    (Replace YUSMARA with your own GitHub org/user.)
# 2. Go to https://deploy.nosana.com/deployments/create
# 3. Paste the contents of nosana_job.json as the job definition
#    (or use the Nosana CLI: `nosana job post --file nosana_job.json`).
# 4. In Deployment Configuration: Strategy = Simple, Replica Count = 1,
#    Container Timeout = 6h. Pick a GPU market that fits the budget —
#    a 0.5B Q4 model runs fine on any GPU; it also runs on CPU, so the
#    cheapest GPU market is enough.
# 5. When the job is running, note the public URL and the Job ID, then:
#        curl https://<job-url>/health
#        curl -X POST https://<job-url>/v1/chat/completions \
#          -H 'Content-Type: application/json' \
#          -d '{"model":"Qwen/Qwen2.5-0.5B-Instruct-GGUF","messages":[{"role":"user","content":"Hello from Nosana"}]}'
# 6. Stop the deployment when done — billing is per uptime hour.
#
# ---------------------------------------------------------------------------
# Verifying a Nosana run
# ---------------------------------------------------------------------------
# - /health returns the model SHA-256. Compare it with the SHA-256 in
#   models/SHA256SUMS — same weights, same answers (temperature 0).
# - Every response carries permainfer_receipt.receipt_id. Fetch the
#   receipt at /receipts/<id> and verify the chain:
#        python -m permainfer.cli verify --ledger <downloaded ledger>
# - The ledger can then be anchored to Arweave (see README § Arweave).
#
# ---------------------------------------------------------------------------
# Cost estimate (from the hackathon announcement's own table)
# ---------------------------------------------------------------------------
# The $70 participant credit is the budget. A small GPU market is
# ~$0.05–0.15/h; a 6-hour demo session is well under $1. An NVIDIA
# 5090 market at $0.48/h would burn $70 in ~145 hours of uptime —
# don't pick it for a 0.5B model. Always use Simple strategy with a
# timeout; never leave a deployment on Infinite.
