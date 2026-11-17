# Research notes — Decentralize AI Hackathon, Round 2
Researched 15 Nov 2026 (WIB) from the official pages below.

## Sources (verified live)
- Official hackathon site + FAQ: https://decentralizeai.tech and https://decentralizeai.tech/faq
- Official announcement (HackerNoon): https://hackernoon.com/compete-for-over-$51k-in-the-decentralize-ai-hackathon-by-hackernoon-nosana-arweave-and-mexc
- Listing: https://devgrantsdaily.com/items/2026-09-06-decentralize-ai-hackathon/
- Nosana job schema: https://learn.nosana.com/deployments/jobs/job-definition/schema.html
- Arweave signing reference (arweave-js): https://github.com/ArweaveTeam/arweave-js (deepHash.ts, transaction.ts, merkle.ts)

## Facts
- Organizers: HackerNoon + Nosana + Arweave + MEXC. Free, online, no deposit, no seed/key asked.
- Rounds: Round 1: 2 Jun – 31 Oct 2026. **Round 2: Nov 2026 – 27 Feb 2027.** Half the prize pool per round.
- Prize pool: **$51,750+** total = $41,750 Nosana compute credits ($70 × 500 participants + $450 × 15 winners) + $2,500 Arweave storage credits (1,000 AR) + $2,500 AR cash prizes (1,000 AR) + $5,000 MEXC MX/USDT rewards. Grand prize: full ownership of the DecentralizeAI.tech domain + codebase.
- Extra $450 prize pool (15 winners) for a follow-up blog post showing how the Nosana credits were used.
- Who can enter: individual developers and early-stage startups, new or existing projects, concept-stage welcome.
- Eligible themes: decentralized GPU orchestration, autonomous AI agents, AI deployment tooling, agent infra/coordination, AI runtime infra, AI developer tooling, scalable inference, AI workflow automation, permanent model storage, verifiable AI systems, open inference infra, data sovereignty tooling.
- Judging: technical depth (real implementation?), originality, impact, verifiable evidence (working code, deployment URL, reproducible metrics). Judges shortlist by readership + quality, then vote. Mockups / prototypes without demos / coming-soon projects are NOT eligible.
- How to enter (two options, both count once published):
  - **Option 1:** Generate a blog on decentralizeai.tech ("Blog It" → topic → email verification → context/strategy/stack/model → generate + publish).
  - **Option 2:** Write on HackerNoon directly, with **at least one sponsored tag**.
- Iteration allowed and encouraged; multiple updates per project.
- Nosana credits: first 500 eligible participants get $70 each. Claim at decentralizeai.tech. Deployments default to "Infinite" strategy + 6h timeout — the announcement warns to switch to **Simple strategy** with a timeout and stop idle instances (5090 market $0.48/h ≈ $350/month 24/7).
- Tags (must include the two universal tags on every submission):
  - Universal: #decentralize-ai, #decentralize-ai-hackathon
  - Nosana: #gpu-markeplace (sic), #gpu-cloud, #ai-compute, #ai-infrastructure, #ai-inference, #gpu-rental, #on-demand-gpus, #scalable-ai-compute, #developer-tools, #cloud-infrastructure, #open-source-gpu-cloud
  - Arweave: #arweave, #decentralized-storage, #permanent-storage
  - HackerNoon: #blockchain, #decentralization, #artificial-intelligence, #programming, #crypto, #open-source, #llms, #agentic-ai, #zero-knowledge-proofs, #technology, #future-of-ai, #dapps, #depin, #decentralized-ai, #cryptography, #web3-development, #decentralized-web, #ai-ethics
  - MEXC: #crypto-ai-trading, #ai-token-liquidity, #ai-agent-tokens
- No country or team-size restrictions listed.

## How PermaInfer maps
- Open inference infra (OpenAI-compatible server, open weights) ✓
- Permanent model storage (receipts + model hashes on Arweave) ✓
- Verifiable AI systems (hash-chained receipts) ✓
- Decentralized GPU orchestration (Nosana job definition) ✓
- Data sovereignty (prompts hashed by default) ✓
