"""PermaInfer server — OpenAI-compatible inference + verifiable receipts.

Endpoints
---------
GET  /health                  liveness + model info
GET  /v1/models               OpenAI-compatible model list
POST /v1/chat/completions     OpenAI-compatible chat completions;
                              every call mints a receipt in the ledger
GET  /receipts                list receipts (newest first, paginated)
GET  /receipts/{receipt_id}   one receipt
GET  /receipts/{receipt_id}/arweave   the exact Arweave payload for a receipt
GET  /ledger/verify           verify the whole receipt chain
POST /ledger/arweave          build the Arweave bundle payload for the
                              whole ledger (dry-run by default; uploads
                              only with --wallet / ARWEAVE_WALLET)

Design notes
------------
* The model backend is pluggable (see :mod:`permainfer.model`). The
  server does not care whether the weights run on a laptop CPU, a
  Nosana GPU node, or the echo stand-in used by the tests — the
  receipt format is identical.
* Receipts are written to the ledger *before* the HTTP response is
  returned, fsync'd, so a receipt can never be lost after a client
  has seen its completion.
* Prompts are stored only as SHA-256 hashes by default. Pass
  ``PERMAINFER_STORE_PLAINTEXT=1`` to also store cleartext (useful for
  a personal demo node; never do this with other people's prompts).
"""

from __future__ import annotations

import os
import socket
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from . import arweave as arweave_mod
from .model import (
    DEFAULT_MODEL_FILE,
    DEFAULT_MODEL_ID,
    EchoBackend,
    GenerationParams,
    LlamaCppBackend,
)
from .receipts import ReceiptLedger, build_receipt


# ---------------------------------------------------------------------------
# Configuration (env vars; no secrets here)
# ---------------------------------------------------------------------------

def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


MODEL_PATH = _env("PERMAINFER_MODEL", f"models/{DEFAULT_MODEL_FILE}")
MODEL_ID = _env("PERMAINFER_MODEL_ID", DEFAULT_MODEL_ID)
LEDGER_PATH = _env("PERMAINFER_LEDGER", "data/ledger.jsonl")
NODE_ID = _env("PERMAINFER_NODE", os.environ.get("NOSANA_JOB_ID") or socket.gethostname())
STORE_PLAINTEXT = _env("PERMAINFER_STORE_PLAINTEXT", "0") == "1"
USE_ECHO = _env("PERMAINFER_BACKEND", "llama") == "echo"


def build_backend():
    if USE_ECHO:
        return EchoBackend()
    return LlamaCppBackend(MODEL_PATH, model_id=MODEL_ID)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = Field(default=MODEL_ID)
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 256
    top_p: float = 0.9
    stream: bool = False


class ArweaveUploadRequest(BaseModel):
    wallet: Optional[str] = None
    dry_run: bool = True


def create_app(backend=None, ledger_path: str | Path = LEDGER_PATH) -> FastAPI:
    backend = backend or build_backend()
    ledger = ReceiptLedger(ledger_path)
    started_at = time.time()

    app = FastAPI(
        title="PermaInfer",
        description=(
            "Open-weight inference with a verifiable receipt for every "
            "completion. Receipts chain by SHA-256 and can be stored "
            "permanently on Arweave."
        ),
        version="0.1.0",
    )

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "model": backend.model_id,
            "model_file": backend.model_file,
            "model_sha256": backend.model_sha256,
            "node": NODE_ID,
            "ledger_entries": len(ledger),
            "uptime_seconds": round(time.time() - started_at, 1),
        }

    @app.get("/v1/models")
    def list_models() -> dict:
        return {
            "object": "list",
            "data": [{
                "id": backend.model_id,
                "object": "model",
                "created": int(started_at),
                "owned_by": "permainfer",
            }],
        }

    @app.post("/v1/chat/completions")
    def chat_completions(req: ChatCompletionRequest) -> dict:
        if req.stream:
            raise HTTPException(400, "streaming is not supported in v0.1.0")
        if req.model not in (backend.model_id, "default"):
            raise HTTPException(404, f"unknown model: {req.model}")
        prompt = "\n".join(f"{m.role}: {m.content}" for m in req.messages)
        params = GenerationParams(
            temperature=req.temperature, max_tokens=req.max_tokens, top_p=req.top_p
        )
        completion, usage = backend.generate(prompt, params)
        receipt = build_receipt(
            prev_receipt_id=ledger.last_receipt_id(),
            model=backend.model_id,
            model_file=backend.model_file,
            model_sha256=backend.model_sha256,
            prompt=prompt,
            completion=completion,
            params=params.to_dict(),
            usage=usage,
            node=NODE_ID,
            store_plaintext=STORE_PLAINTEXT,
        )
        ledger.append(receipt)
        return {
            "id": f"chatcmpl-{receipt.receipt_id[:24]}",
            "object": "chat.completion",
            "created": int(receipt.created_at),
            "model": backend.model_id,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": completion},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            "permainfer_receipt": {
                "receipt_id": receipt.receipt_id,
                "prev_receipt_id": receipt.prev_receipt_id,
                "prompt_sha256": receipt.prompt_sha256,
                "completion_sha256": receipt.completion_sha256,
                "model_sha256": receipt.model_sha256,
                "verify": f"/receipts/{receipt.receipt_id}",
            },
        }

    @app.get("/receipts")
    def list_receipts(limit: int = Query(20, ge=1, le=100)) -> dict:
        receipts = ledger.load_all()
        receipts.reverse()
        return {"count": len(receipts), "receipts": [r.to_dict() for r in receipts[:limit]]}

    @app.get("/receipts/{receipt_id}")
    def get_receipt(receipt_id: str) -> dict:
        for r in ledger.load_all():
            if r.receipt_id == receipt_id:
                return r.to_dict()
        raise HTTPException(404, f"receipt not found: {receipt_id}")

    @app.get("/receipts/{receipt_id}/arweave")
    def get_receipt_arweave(receipt_id: str) -> dict:
        for r in ledger.load_all():
            if r.receipt_id == receipt_id:
                return arweave_mod.receipt_to_arweave_payload(r)
        raise HTTPException(404, f"receipt not found: {receipt_id}")

    @app.get("/ledger/verify")
    def verify_ledger() -> dict:
        ok, problems = ledger.verify()
        return {"ok": ok, "entries": len(ledger), "problems": problems}

    @app.post("/ledger/arweave")
    def ledger_arweave(req: ArweaveUploadRequest) -> dict:
        receipts = ledger.load_all()
        payload = arweave_mod.ledger_to_arweave_payload(receipts)
        if req.dry_run:
            return {
                "dry_run": True,
                "receipt_count": len(receipts),
                "payload_bytes": len(payload["data_json"]),
                "tags": payload["tags"],
                "note": "Dry run only — nothing was uploaded. Pass dry_run=false "
                        "with a wallet to upload (costs AR).",
            }
        try:
            result = arweave_mod.upload_payload(payload, wallet_path=req.wallet)
        except Exception as exc:  # noqa: BLE001 - surfaced as HTTP 400
            raise HTTPException(400, str(exc))
        return {"dry_run": False, **result, "receipt_count": len(receipts)}

    return app


app = create_app() if os.environ.get("PERMAINFER_NO_AUTOSTART") != "1" else None


def create_app_factory() -> FastAPI:
    """Uvicorn factory: builds the app (and loads the model) at serve time.

    Use with ``uvicorn --factory permainfer.server:create_app_factory``.
    Importing this module never loads a model — the factory does.
    """
    return create_app()


def main() -> None:
    import uvicorn

    host = _env("PERMAINFER_HOST", "0.0.0.0")
    port = int(_env("PERMAINFER_PORT", "8000"))
    uvicorn.run("permainfer.server:create_app_factory", host=host, port=port, factory=True)


if __name__ == "__main__":
    main()
