---
Title: "Trust, but Verify": Building Verifiable Open-Weight Inference on Nosana and Arweave
Tags: #decentralize-ai #decentralize-ai-hackathon #ai-inference #nosana #arweave #open-source #ai-infrastructure #gpu-marketplace #decentralized-storage #permanent-storage
Suggested HackerNoon tags: decentralize-ai, decentralize-ai-hackathon, ai-inference, nosana, arweave, open-source, ai-infrastructure, gpu-marketplace, decentralized-storage, permanent-storage
Status: DRAFT — not published. Publish on HackerNoon (Option 2: write directly) and submit the project at decentralizeai.tech. See SUBMISSION.md.
---

# "Trust, but Verify": Building Verifiable Open-Weight Inference on Nosana and Arweave

Open-weight models were supposed to fix AI's trust problem. The weights
are public, the licenses are permissive, anyone can download them — and
yet, when you actually *use* an open model through a hosted API, you are
back to trusting a stranger. Which weights are really loaded? Was the
model quietly swapped overnight? Is there a hidden system prompt steering
the answers? And if an output ever matters — a decision, a quote, a piece
of evidence — where is the record?

I built **PermaInfer** to answer those questions with cryptography
instead of promises: an OpenAI-compatible inference server for
open-weight models where every single completion comes with a verifiable
receipt, the receipts chain together in a tamper-evident ledger, and the
ledger can be anchored permanently on Arweave — while the compute itself
runs on Nosana's decentralized GPU network.

This post is the build log: the problem, the architecture, the demo, and
what I verified. The code is open source (MIT) and the whole thing runs
locally for free.

## The problem: open weights, closed execution

The open-model ecosystem has made extraordinary progress. A 0.5B
parameter instruction-tuned model that fits on a laptop can hold a
coherent conversation; larger open models rival proprietary ones on many
benchmarks. But the *serving* layer has not kept up. In practice, most
people consume open models through a hosted endpoint — and at that point
three things break:

1. **You cannot check what ran.** An API can serve any weights behind
   any label. There is no mechanism for a client to confirm that the
   model answering is the model advertised.
2. **There is no record.** Inference is ephemeral. There is no durable,
   third-party-verifiable artifact that says "this prompt produced this
   completion, from these weights, at this time."
3. **The infrastructure is still centralized.** Even open models usually
   run on the same few clouds. Decentralizing the weights without
   decentralizing the compute is half a job.

These are infrastructure problems, and they are exactly what the
Decentralize AI Hackathon is about: open inference infrastructure,
permanent storage, verifiable systems, and decentralized compute. So I
built one system that touches all four.

## The idea: a receipt for every inference

The core idea is deliberately boring — it is just hashing, done
carefully:

- Every completion produces a **receipt**: the model id, the SHA-256 of
  the exact weight file loaded, the SHA-256 of the exact prompt, the
  SHA-256 of the exact completion, the generation parameters, token
  usage, node id, and timestamp.
- Receipts are **chained**: each receipt contains the SHA-256 of the
  previous receipt. The ledger is an append-only JSONL file, and editing
  any historical entry breaks every hash after it.
- A receipt maps 1:1 to an **Arweave transaction**: the receipt JSON is
  the data, and ANS-110 tags (`App-Name: PermaInfer`, `Model-SHA256`,
  `Receipt-ID`, …) make it discoverable. Upload it once and the record
  is permanent and public at `arweave.net/<txid>`.
- The server itself runs on **Nosana**, so the GPU doing the work is
  rented from the decentralized network, not a hyperscaler.

Nothing here requires trusting me, the operator, or any single server.
Anyone with the receipt can recompute the hashes; anyone with the ledger
can re-verify the chain; anyone with the Arweave tx id can fetch the
record forever.

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

**The model.** Qwen2.5-0.5B-Instruct (Apache 2.0), quantized to Q4_K_M
GGUF — about 491 MB. Small enough to run on a CPU for development and
on any Nosana GPU for production, real enough to be a genuine language
model rather than a toy. The server records the SHA-256 of the weight
file it actually loaded, so "which model" is a checkable fact, not a
config claim. Swap in any GGUF model by pointing at a different file.

**The server.** FastAPI, OpenAI-compatible: `POST /v1/chat/completions`
works with any OpenAI client library. The response carries a
`permainfer_receipt` block with the receipt id and the hashes. Receipt
endpoints (`/receipts`, `/receipts/{id}`, `/receipts/{id}/arweave`,
`/ledger/verify`) expose the whole verifiability layer over HTTP.

**The ledger.** Append-only, fsync'd before the HTTP response is
returned — a receipt can never be lost after a client has seen its
completion. Verification is a single offline command:
`permainfer verify` re-hashes every receipt and checks every link.

**The Arweave layer.** Two functions, strictly separated. The payload
builder is pure and offline: it turns a receipt (or a whole ledger
bundle) into the exact JSON document and tags that will be stored, so
anyone can inspect what will be uploaded before a single winston is
spent. The uploader signs a standard Arweave format-2 transaction —
tagged SHA-384 deep-hash, SHA-256 merkle `data_root`, RSA-PSS/SHA-256
signature — ported directly from the public arweave-js reference code.
The wallet JWK is supplied at runtime only, never stored, never logged.
A ~1 KB receipt costs a fraction of a cent in AR; bundling the whole
ledger into one transaction is cheaper still.

**Privacy by default.** Prompts are stored only as SHA-256 hashes. The
ledger proves *what* was asked without revealing it — verification needs
the prompt, which only the person who asked it has. Cleartext storage is
an explicit opt-in for personal demo nodes, never the default.

## Demo: from prompt to permanent record

The repo ships a one-command demo (`./demo.sh`). Here is what it does,
against a local node:

```bash
$ curl -s http://localhost:8000/health
{
  "status": "ok",
  "model": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
  "model_file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
  "model_sha256": "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db",
  "node": "htch-runtime",
  "ledger_entries": 0
}
```

```bash
$ curl -s -X POST http://localhost:8000/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{"model":"Qwen/Qwen2.5-0.5B-Instruct-GGUF",
         "messages":[{"role":"user","content":"In one sentence, why should AI infrastructure be decentralized?"}]}'
{
  "id": "chatcmpl-a7d976ada52db2b2",
  "choices": [{ "message": { "role": "assistant",
    "content": "Decentralized AI infrastructure allows for greater control and security over AI algorithms and data, reducing the risk of centralized control and enabling more robust and secure AI systems." } }],
  "usage": { "prompt_tokens": 32, "completion_tokens": 32, "total_tokens": 64 },
  "permainfer_receipt": {
    "receipt_id": "a7d976ada52db2b2ce179b4739551801e63c396f754d48e33ec253cb5685722c",
    "prompt_sha256": "b7585523b0752c58b624aafe3750625b0823e9763ff8a8c9480b555033867e62",
    "completion_sha256": "76de18ea38ff3d1c2bc25027020f1cd2ecdc1950b3117cc2c7dbc73e246b2184",
    "model_sha256": "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
  }
}
```

Then the verification anyone can run, no trust required:

```bash
$ permainfer verify --ledger data/ledger.jsonl
ledger: data/ledger.jsonl  entries: 1
OK — receipt chain intact, all hashes match.

$ permainfer arweave-payload --ledger data/ledger.jsonl --receipt a7d976ada52d…
# → the exact JSON + tags that anchor this receipt on Arweave.
#    Dry run only: nothing uploaded, nothing spent.
```

And to prove the tamper-evidence is real, not decorative, I tested it:
edit one byte of a historical receipt in the ledger and `permainfer
verify` fails with a hash mismatch on that entry — the chain catches it
immediately. That test is in the repo's suite (`pytest -q`, 15 tests,
no model, no network, no wallet needed).

## Running it on Nosana

The repo includes a ready-to-post Nosana job definition
(`nosana/nosana_job.json`): one container, the PermaInfer image with
weights baked in, port 8000 exposed, Simple strategy, 1 replica,
6-hour timeout. Two things I learned from the hackathon docs that
shaped this:

- **Never use the default Infinite strategy.** It keeps the instance
  running until your credits run out — with a 5090 market at $0.48/h,
  $70 of credit is gone in ~145 hours. Simple strategy with a timeout,
  stop when idle.
- **A 0.5B model does not need a 5090.** Pick the cheapest GPU market
  that fits; a demo session costs well under a dollar.

Once the job is running, verification works exactly the same as locally:
`/health` returns the model SHA-256 (compare it with the published
`SHA256SUMS` in the repo), every response carries a receipt id, and the
ledger can be downloaded, verified, and anchored to Arweave.

## What this is — and what it is not

**What it is:** a working, minimal piece of verifiable AI
infrastructure. Real model, real inference, real receipts, real Arweave
transaction format, real Nosana job definition — all reproducible from
the repo with no account and no payment.

**What it is not:** a proof that the *computation* was correct. A
receipt proves which weights, prompt, and completion are claimed — it
does not prove the node actually ran those weights. That is the next
layer (remote attestation, TEEs, or zkML proofs of inference), and it is
deliberately out of scope for this build. Receipts make cheating
*detectable* — a node that serves different weights than it claims will
produce completions that do not match a re-run — but detection still
needs someone to re-run and compare. Honest infrastructure starts with
making the claim checkable; this project does that part.

Two more honest limitations: the Arweave signer is ported from the
public arweave-js source but has not yet been validated against a live
transaction, because that needs a funded wallet — the first real upload
should be a tiny test transaction. And the $70 Nosana credit claim is a
human step I cannot do on anyone's behalf.

## Why this matters

Centralized AI asks you to trust the operator about everything that
matters: what model ran, what it was told, what it said, and whether
the record still exists. Open weights alone do not fix that — they fix
the *model*, not the *execution*.

Verifiable receipts fix the execution record. Decentralized compute
fixes who runs it. Permanent storage fixes whether the record survives.
None of these is exotic technology: it is hashing, an append-only log,
a content-addressed store, and a GPU marketplace. Put together, they
turn "trust us" into "check us" — and that is the whole point of
decentralized AI infrastructure.

## Try it

- **Repo:** <link to the public repository — add when published>
- **Quickstart:** `python scripts/download_model.py && python -m permainfer.cli serve`
- **Demo:** `./demo.sh`
- **Verify:** `permainfer verify --ledger data/ledger.jsonl`
- **Hackathon:** Round 2 runs November 2026 – 27 February 2027 at
  [decentralizeai.tech](https://decentralizeai.tech). First 500 eligible
  participants get $70 in Nosana compute credits.

If you run a node, publish your receipts. If you build on this, the
receipt format is open — the best infrastructure is the kind anyone can
check.

---

*PermaInfer is an independent entry for the Decentralize AI Hackathon
(Round 2), built with Qwen2.5-0.5B-Instruct (Apache 2.0), llama.cpp,
Nosana, and Arweave. No affiliation with HackerNoon, Nosana, Arweave,
or MEXC beyond participation in the hackathon.*
