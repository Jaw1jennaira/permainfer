# PermaInfer — Verifiable Open-Weight Inference on Decentralized Infrastructure

> **Decentralize AI Hackathon (HackerNoon × Nosana × Arweave × MEXC), Round 2 — entry.**
> Round 2 runs November 2026 – 27 February 2027. This repo is the working
> project behind the submission; the HackerNoon article draft is in
> [`blog/hackernoon-draft.md`](blog/hackernoon-draft.md).

## The problem

Centralized AI has a trust problem, and it is not about the models — the
weights are increasingly open. It is about **what happens when you run
them**:

1. **You cannot check what ran.** A hosted API can serve any weights, any
   system prompt, any silently-updated model, and you have no way to tell.
2. **There is no record.** When an inference matters — a decision, a quote,
   a piece of evidence — there is nothing permanent to point at. Logs live
   on someone else's server and can be edited or deleted.
3. **The infrastructure is rented from the same few clouds.** Even "open"
   models usually run on centralized GPU fleets.

PermaInfer fixes the first two with cryptography that anyone can verify,
and the third by running on Nosana's decentralized GPU network and
anchoring its records on Arweave's permanent storage.

## What it is

An **OpenAI-compatible inference server for open-weight models** where
every completion comes with a **verifiable receipt**:

- The server runs a real open-weight model — **Qwen2.5-0.5B-Instruct**
  (Apache 2.0, Q4_K_M GGUF, ~491 MB) — via llama.cpp. No API keys, no
  hosted model provider.
- Every `/v1/chat/completions` call mints a **receipt**: model id, SHA-256
  of the exact weights loaded, SHA-256 of the exact prompt, SHA-256 of the
  exact completion, generation parameters, token usage, node id, timestamp.
- Receipts are chained — each one carries the SHA-256 of the previous
  receipt — in an append-only JSONL **ledger**. Edit any historical entry
  and every hash after it breaks. `permainfer verify` checks the whole
  chain offline.
- Each receipt maps 1:1 to an **Arweave transaction payload** (ANS-110
  tags: `App-Name: PermaInfer`, `Model-SHA256`, `Receipt-ID`, …). The
  payload is built offline and for free; uploading it makes the receipt
  permanent and publicly verifiable at `arweave.net/<txid>`.
- The same server runs on **Nosana** — see [`nosana/nosana_job.json`](nosana/nosana_job.json)
  — so the compute itself is decentralized too.

## Architecture

```
                ┌──────────────────────────────────────────────┐
  client ─────► │  PermaInfer server (FastAPI, OpenAI-compatible)
  (any OpenAI   │    ├─ llama.cpp backend (Qwen2.5-0.5B, GGUF)
  client)       │    ├─ receipts: SHA-256 chain, JSONL ledger
                │    └─ Arweave payload builder (offline)
                └──────┬───────────────────────┬───────────────┘
                       │ runs on               │ anchors to
              ┌────────▼────────┐      ┌───────▼────────┐
              │  Nosana GPU node │      │  Arweave       │
              │  (decentralized  │      │  (permanent,   │
              │   compute)       │      │   public)      │
              └─────────────────┘      └────────────────┘
```

**What is verified, and by whom:**

| Claim | How anyone checks it |
|---|---|
| These exact weights produced this answer | `/health` returns `model_sha256`; compare with `models/SHA256SUMS`; re-run with temperature 0 |
| This prompt produced this completion | Receipt stores `prompt_sha256` + `completion_sha256`; recompute from your own copy |
| No receipt was altered or deleted | `permainfer verify` re-hashes the whole chain |
| The record is permanent | Receipt is an Arweave tx; fetch it at `arweave.net/<txid>` |

## Quickstart (free, no account)

```bash
git clone <this-repo> && cd permainfer
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .

# 1. Get the model (free, Hugging Face, no account)
python scripts/download_model.py        # ~491 MB, prints its SHA-256

# 2. Run the server
python -m permainfer.cli serve --port 8000

# 3. Ask it something (any OpenAI client works)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen2.5-0.5B-Instruct-GGUF",
       "messages":[{"role":"user","content":"Why decentralize AI?"}]}'

# 4. Verify the receipt chain
python -m permainfer.cli verify --ledger data/ledger.jsonl

# 5. See the exact Arweave payload (dry run — nothing uploaded, nothing spent)
python -m permainfer.cli arweave-payload --ledger data/ledger.jsonl
```

Or run the whole demo in one command: `./demo.sh` (uses the echo backend
if no model file is present — receipts are still real).

**Tests:** `pytest -q` — 15 tests, no model, no network, no wallet.

## API

| Endpoint | What it does |
|---|---|
| `GET /health` | Liveness + model id, file, SHA-256, node, ledger size |
| `GET /v1/models` | OpenAI-compatible model list |
| `POST /v1/chat/completions` | Chat completion; response includes `permainfer_receipt` |
| `GET /receipts` | List receipts (newest first) |
| `GET /receipts/{id}` | One receipt |
| `GET /receipts/{id}/arweave` | The exact Arweave payload for that receipt |
| `GET /ledger/verify` | Verify the whole chain |
| `POST /ledger/arweave` | Dry-run bundle payload, or upload with a wallet |

## Nosana (decentralized compute)

The job definition in [`nosana/nosana_job.json`](nosana/nosana_job.json)
runs this exact server on a Nosana GPU node: 1 replica, Simple strategy,
6-hour timeout, port 8000 exposed. Full steps + cost notes are in
[`nosana/README.md`](nosana/README.md). Launching it is a **user step**:
it needs a Nosana account and the hackathon's $70 compute credit
(claimed at decentralizeai.tech) — no money from this repo is ever spent.

## Arweave (permanent storage)

```bash
# Build the payload for the whole ledger (offline, free):
python -m permainfer.cli arweave-payload --ledger data/ledger.jsonl --out payload.json

# Upload it (user step — needs a funded Arweave wallet JWK):
python -m permainfer.cli arweave-upload --ledger data/ledger.jsonl --wallet wallet.json
# → https://arweave.net/<txid>
```

The uploader signs a standard Arweave format-2 transaction (tagged
SHA-384 deep-hash, SHA-256 merkle `data_root`, RSA-PSS/SHA-256) — a
direct port of the public arweave-js reference code. The wallet JWK is
read at runtime only, never stored or logged. A ~1 KB receipt costs a
fraction of a cent in AR; bundling the whole ledger into one transaction
is cheaper still.

**Honest limitation:** the signer has not yet been validated against a
live Arweave transaction (that needs a funded wallet). Validate it with
a tiny test upload before relying on it for a production ledger.

## Privacy

By default prompts are stored **only as SHA-256 hashes** — the ledger
proves *what* was asked without revealing it. Set
`PERMAINFER_STORE_PLAINTEXT=1` only on a personal demo node, never with
other people's prompts.

## Project layout

```
permainfer/
├── src/permainfer/
│   ├── server.py      FastAPI app (OpenAI-compatible + receipt endpoints)
│   ├── model.py       backends: llama.cpp (real) + echo (tests only)
│   ├── receipts.py    canonical hashing, chained receipt ledger
│   ├── arweave.py     payload builder, merkle root, tx signer, uploader
│   └── cli.py         verify / arweave-payload / arweave-upload / serve
├── scripts/download_model.py   free GGUF download from Hugging Face
├── tests/             13 tests (receipts, chain, Arweave, API, signing)
├── nosana/            job definition + deploy notes
├── blog/              HackerNoon article draft
├── demo.sh            end-to-end demo
├── Dockerfile         self-contained image (model baked in)
└── SUBMISSION.md      what is ready to submit + the user steps
```

## Hackathon fit

| Hackathon theme | How PermaInfer maps |
|---|---|
| Open inference infrastructure | OpenAI-compatible server for open weights, no vendor lock-in |
| Permanent model storage | Receipts + model hashes anchored on Arweave |
| Verifiable AI systems | Hash-chained receipts; anyone can re-verify prompt → completion |
| Decentralized GPU orchestration | Runs on Nosana via a published job definition |
| Data sovereignty | Prompts stored as hashes by default; operator owns the ledger |

## License

MIT. Model weights: Qwen2.5-0.5B-Instruct, Apache 2.0 (Alibaba Qwen team).
