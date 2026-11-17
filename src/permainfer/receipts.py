"""Canonical hashing + append-only receipt ledger.

Every inference served by PermaInfer produces a *receipt*: a small JSON
document that binds together the model identity, the exact prompt, the
exact completion, and the generation parameters. Receipts are chained —
each one carries the SHA-256 of the previous receipt — so the ledger is
tamper-evident: editing any historical entry breaks every hash after it.

A receipt is also the exact payload that gets stored permanently on
Arweave (see :mod:`permainfer.arweave`). Nothing in a receipt contains a
secret: prompts are hashed, not stored in cleartext, unless the operator
explicitly opts into storing the full text (``store_plaintext``).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

APP_NAME = "PermaInfer"
APP_VERSION = "0.1.0"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> bytes:
    """Deterministic JSON encoding: sorted keys, no whitespace.

    Canonical encoding is what makes a receipt verifiable by anyone,
    anywhere, with any JSON implementation.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass
class Receipt:
    """One verifiable inference receipt."""

    receipt_id: str          # sha256 of the canonical receipt body
    prev_receipt_id: str     # "" for the genesis receipt, else previous id
    created_at: float        # unix timestamp (seconds)
    model: str               # model id, e.g. "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
    model_file: str          # GGUF filename served
    model_sha256: str        # sha256 of the model file actually loaded
    prompt_sha256: str       # sha256 of the exact prompt text sent to the model
    completion_sha256: str   # sha256 of the exact completion text returned
    params: dict             # generation parameters (temperature, max_tokens, ...)
    usage: dict              # prompt/completion token counts + wall time
    node: str                # node id serving the request (hostname or Nosana job id)
    prompt: Optional[str] = field(default=None)       # cleartext, only if opted in
    completion: Optional[str] = field(default=None)   # cleartext, only if opted in

    def body(self) -> dict:
        """The canonical body that is hashed to produce ``receipt_id``."""
        d = asdict(self)
        d.pop("receipt_id")
        return d

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Receipt":
        return cls(**d)


def build_receipt(
    *,
    prev_receipt_id: str,
    model: str,
    model_file: str,
    model_sha256: str,
    prompt: str,
    completion: str,
    params: dict,
    usage: dict,
    node: str,
    store_plaintext: bool = False,
    created_at: Optional[float] = None,
) -> Receipt:
    """Build a receipt and compute its id from its canonical body."""
    receipt = Receipt(
        receipt_id="",
        prev_receipt_id=prev_receipt_id,
        created_at=created_at if created_at is not None else time.time(),
        model=model,
        model_file=model_file,
        model_sha256=model_sha256,
        prompt_sha256=sha256_hex(prompt.encode("utf-8")),
        completion_sha256=sha256_hex(completion.encode("utf-8")),
        params=params,
        usage=usage,
        node=node,
        prompt=prompt if store_plaintext else None,
        completion=completion if store_plaintext else None,
    )
    receipt.receipt_id = sha256_hex(canonical_json(receipt.body()))
    return receipt


class ReceiptLedger:
    """Append-only JSONL ledger of receipts, with chain verification.

    Each line is one receipt as compact JSON. The ledger file is the
    local, auditable copy; the permanent copy lives on Arweave once the
    operator uploads it (see :mod:`permainfer.arweave`).
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def __len__(self) -> int:
        return sum(1 for _ in self._iter_lines())

    def _iter_lines(self):
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield line

    def last_receipt_id(self) -> str:
        last = ""
        for line in self._iter_lines():
            last = json.loads(line)["receipt_id"]
        return last

    def append(self, receipt: Receipt) -> Receipt:
        """Append a receipt. Refuses to append if the chain is broken."""
        expected_prev = self.last_receipt_id()
        if receipt.prev_receipt_id != expected_prev:
            raise ValueError(
                f"receipt prev {receipt.prev_receipt_id!r} != ledger tip {expected_prev!r}; "
                "refusing to append — rebuild the receipt against the current tip"
            )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return receipt

    def load_all(self) -> list[Receipt]:
        return [Receipt.from_dict(json.loads(line)) for line in self._iter_lines()]

    def verify(self) -> tuple[bool, list[str]]:
        """Verify the whole chain. Returns (ok, list_of_problems)."""
        problems: list[str] = []
        prev = ""
        for i, receipt in enumerate(self.load_all()):
            if receipt.prev_receipt_id != prev:
                problems.append(f"receipt #{i} ({receipt.receipt_id[:12]}…): prev link broken")
            recomputed = sha256_hex(canonical_json(receipt.body()))
            if recomputed != receipt.receipt_id:
                problems.append(f"receipt #{i} ({receipt.receipt_id[:12]}…): id hash mismatch — content was altered")
            prev = receipt.receipt_id
        return (not problems, problems)
