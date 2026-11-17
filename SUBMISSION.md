# SUBMISSION — Decentralize AI Hackathon, Round 2 (#31)

Project: **PermaInfer** — verifiable open-weight inference on Nosana + Arweave.
Status: **BUILT, TESTED, READY TO SUBMIT — pending user steps below.**
Nothing has been submitted, registered, or paid anywhere. No accounts created.

## What is ready
- [x] Working code: FastAPI inference server (OpenAI-compatible), llama.cpp backend
      (Qwen2.5-0.5B-Instruct GGUF), hash-chained receipt ledger, Arweave payload
      builder + tx signer, CLI, 15 passing tests, demo script, Dockerfile.
- [x] Live-verified locally: real model inference + receipt minting + chain
      verification (see `demo/demo-run-real-model.log`, `demo/ledger-demo.jsonl`,
      `demo/arweave-payload-bundle.json`).
- [x] Nosana job definition: `nosana/nosana_job.json` (validated JSON, schema-checked
      against learn.nosana.com).
- [x] HackerNoon blog draft: `blog/hackernoon-draft.md` (English, HackerNoon style,
      with required tags listed in the frontmatter).
- [x] README with architecture, quickstart, API, and honest limitations.
- [x] Research notes: `RESEARCH.md` (rules, prizes, judging, tags, sources).

## User steps (SISA USER — nothing here can be done by the agent)
1. **Publish the repo** (e.g. GitHub, public) and replace the `<link to the public
   repository>` placeholder in `blog/hackernoon-draft.md`.
2. **HackerNoon account** — needed to publish the blog (Option 2). Free signup at
   hackernoon.com. Publish the draft, selecting at least one sponsored tag
   (recommended: #decentralize-ai, #decentralize-ai-hackathon, #ai-inference,
   #nosana, #arweave, #open-source, #ai-infrastructure).
3. **Submit the project at https://decentralizeai.tech** (Option 1 flow also
   possible: "Blog It" → paste the draft → verify email → publish). Submitting
   the published post officially enters the hackathon.
4. **Claim the $70 Nosana credits** at decentralizeai.tech (first 500 eligible
   participants) — needs a Nosana account + wallet connection. Then deploy
   `nosana/nosana_job.json` (see `nosana/README.md`; use Simple strategy, 1
   replica, 6h timeout; stop when idle). This is optional for entry but
   strengthens the submission and qualifies for the extra $450 follow-up prize.
5. **(Optional, costs a little AR) Arweave upload**: fund an Arweave wallet,
   then `python -m permainfer.cli arweave-upload --ledger data/ledger.jsonl
   --wallet wallet.json`. Validate the signer first with a tiny test upload
   (see README "Honest limitation"). A follow-up blog post showing the Nosana
   credit usage qualifies for the additional $450 prize pool.
6. **(Optional) Follow-up post**: after the Nosana run, publish a second
   HackerNoon post showing how the credits were used (required for the $450
   Nosana winner credits).

## Accounts / wallets the user needs (none needed by the agent)
- HackerNoon account (to publish + submit).
- GitHub account (to publish the repo — or any public git host).
- Nosana account + Solana wallet (only for claiming credits + deploying).
- Arweave wallet JWK (only for the optional permanent upload; costs a small
  amount of AR — a ~1 KB receipt is a fraction of a cent).

## What was NOT done (honest limitations)
- No live Nosana deployment: needs the user's account + claimed credits.
- No live Arweave upload: needs the user's funded wallet; the signer is
  implemented from the public arweave-js source but not yet validated
  against a live transaction.
- No HackerNoon/decentralizeai.tech submission: needs the user's accounts.
- No money spent anywhere in this build (model + tools are free).

## Deadline
Round 2 ends **27 February 2027**. Winners announced at the end of the round.
Prizes are judged (readership + quality), not guaranteed.
