"""Arweave payload builder + uploader.

A PermaInfer receipt becomes permanent by storing it on Arweave.
This module keeps two things strictly separate:

1. :func:`receipt_to_arweave_payload` / :func:`ledger_to_arweave_payload`
   — pure, offline, no keys, no network. They turn receipts into the
   exact JSON document + ANS-110-style tags that will be uploaded.
   Anyone can inspect a payload and verify it against the local ledger
   *before* anything is spent.
2. :func:`upload_payload` — the only network call. Signs a standard
   Arweave format-2 data transaction with a wallet JWK supplied by the
   operator at runtime (``--wallet path/to/wallet.json`` or the
   ``ARWEAVE_WALLET`` env var) and POSTs it to a gateway. The JWK is
   never written to disk by this code, never logged, and never
   committed. Without a wallet the function refuses to run — use
   ``--dry-run`` to produce the payload instead.

The signing code is a direct port of the public arweave-js reference
implementation (``ArweaveTeam/arweave-js``: ``src/common/lib/deepHash.ts``,
``src/common/lib/transaction.ts``, ``src/common/lib/merkle.ts``):
tagged SHA-384 deep-hash for the signature data, SHA-256 merkle tree
for ``data_root``, RSA-PSS/SHA-256 signature, tx id = SHA-256(signature).

Honest limitation: this signer has NOT yet been validated against a
live Arweave transaction, because that requires a funded wallet (a
user step). Before the first real upload, validate it with a tiny
test transaction and confirm the tx id resolves on arweave.net.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Union

import httpx

from .receipts import APP_NAME, APP_VERSION, Receipt, canonical_json

ARWEAVE_GATEWAY = "https://arweave.net"

MAX_CHUNK_SIZE = 256 * 1024
MIN_CHUNK_SIZE = 32 * 1024


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _sha384(data: bytes) -> bytes:
    return hashlib.sha384(data).digest()


# ---------------------------------------------------------------------------
# Arweave deep-hash (arweave-js deepHash.ts, tagged scheme)
# ---------------------------------------------------------------------------

def deep_hash(data: Union[bytes, list]) -> bytes:
    """Tagged deep-hash. ``data`` is bytes (blob) or a list (list)."""
    if isinstance(data, list):
        tag = b"list" + str(len(data)).encode()
        acc = _sha384(tag)
        for chunk in data:
            acc = _sha384(acc + deep_hash(chunk))
        return acc
    tag = b"blob" + str(len(data)).encode()
    return _sha384(_sha384(tag) + _sha384(data))


# ---------------------------------------------------------------------------
# Arweave merkle tree / data_root (arweave-js merkle.ts)
# ---------------------------------------------------------------------------

def _int_to_buffer(note: int) -> bytes:
    return note.to_bytes(32, "big")


def compute_data_root(data: bytes) -> bytes:
    """data_root for a transaction: merkle root over 256 KiB chunks.

    Single-chunk payloads (every receipt / ledger bundle we produce)
    reduce to: leaf = SHA256(SHA256(SHA256(data)) || SHA256(len(data)
    as 32-byte big-endian)); root = leaf.
    """
    # chunkData
    chunks: list[tuple[bytes, int, int]] = []  # (dataHash, min, max)
    rest, cursor = data, 0
    while len(rest) >= MAX_CHUNK_SIZE:
        chunk_size = MAX_CHUNK_SIZE
        next_size = len(rest) - MAX_CHUNK_SIZE
        if 0 < next_size < MIN_CHUNK_SIZE:
            chunk_size = (len(rest) + 1) // 2
        chunk = rest[:chunk_size]
        chunks.append((_sha256(chunk), cursor, cursor + len(chunk)))
        cursor += len(chunk)
        rest = rest[chunk_size:]
    chunks.append((_sha256(rest), cursor, cursor + len(rest)))

    # generateLeaves
    leaves: list[dict] = []
    for data_hash, min_range, max_range in chunks:
        leaf_id = _sha256(_sha256(data_hash) + _sha256(_int_to_buffer(max_range)))
        leaves.append({"id": leaf_id, "max": max_range})

    # buildLayers
    def hash_branch(left: dict, right: dict) -> dict:
        branch_id = _sha256(
            _sha256(left["id"]) + _sha256(right["id"]) + _sha256(_int_to_buffer(left["max"]))
        )
        return {"id": branch_id, "max": right["max"]}

    nodes = leaves
    while len(nodes) >= 2:
        next_layer = []
        for i in range(0, len(nodes), 2):
            if i + 1 < len(nodes):
                next_layer.append(hash_branch(nodes[i], nodes[i + 1]))
            else:
                next_layer.append(nodes[i])
        nodes = next_layer
    return nodes[0]["id"]


# ---------------------------------------------------------------------------
# Payloads (offline, keyless)
# ---------------------------------------------------------------------------

def receipt_tags(receipt: Receipt) -> list[dict[str, str]]:
    """ANS-110 style tags so the receipt is discoverable on Arweave."""
    return [
        {"name": "App-Name", "value": APP_NAME},
        {"name": "App-Version", "value": APP_VERSION},
        {"name": "Content-Type", "value": "application/json"},
        {"name": "Type", "value": "inference-receipt"},
        {"name": "Model", "value": receipt.model},
        {"name": "Model-File", "value": receipt.model_file},
        {"name": "Model-SHA256", "value": receipt.model_sha256},
        {"name": "Receipt-ID", "value": receipt.receipt_id},
        {"name": "Prev-Receipt-ID", "value": receipt.prev_receipt_id or "genesis"},
        {"name": "Prompt-SHA256", "value": receipt.prompt_sha256},
        {"name": "Completion-SHA256", "value": receipt.completion_sha256},
        {"name": "Node", "value": receipt.node},
    ]


def receipt_to_arweave_payload(receipt: Receipt) -> dict[str, Any]:
    """Offline, keyless: the exact document + tags for one receipt."""
    data = receipt.to_dict()
    return {
        "data": data,
        "tags": receipt_tags(receipt),
        "data_json": canonical_json(data).decode("utf-8"),
    }


def ledger_to_arweave_payload(receipts: list[Receipt]) -> dict[str, Any]:
    """Bundle a whole ledger into ONE Arweave document (cheaper).

    The bundle keeps every receipt intact, plus a manifest with the
    chain tip, so a single transaction anchors the entire history.
    """
    data = {
        "app": APP_NAME,
        "version": APP_VERSION,
        "type": "inference-receipt-bundle",
        "count": len(receipts),
        "tip_receipt_id": receipts[-1].receipt_id if receipts else "",
        "receipts": [r.to_dict() for r in receipts],
    }
    tags = [
        {"name": "App-Name", "value": APP_NAME},
        {"name": "App-Version", "value": APP_VERSION},
        {"name": "Content-Type", "value": "application/json"},
        {"name": "Type", "value": "inference-receipt-bundle"},
        {"name": "Receipt-Count", "value": str(len(receipts))},
        {"name": "Tip-Receipt-ID", "value": data["tip_receipt_id"] or "empty"},
    ]
    return {"data": data, "tags": tags, "data_json": canonical_json(data).decode("utf-8")}


# ---------------------------------------------------------------------------
# Signing + upload (needs a wallet JWK supplied by the operator)
# ---------------------------------------------------------------------------

def _load_wallet(path: str | Path) -> dict:
    wallet_path = Path(path)
    if not wallet_path.exists():
        raise FileNotFoundError(f"Arweave wallet not found: {wallet_path}")
    return json.loads(wallet_path.read_text(encoding="utf-8"))


def build_transaction(payload: dict[str, Any], wallet: dict, reward: str, last_tx: str) -> dict[str, Any]:
    """Build + sign a standard Arweave format-2 data transaction.

    ``reward`` (winston) and ``last_tx`` (network anchor) come from the
    gateway; callers fetch them live. Signature data order follows
    arweave-js ``Transaction.getSignatureData`` (format 2):
    [format, owner, target, quantity, reward, last_tx, tagList,
    data_size, data_root], deep-hashed; signed RSA-PSS/SHA-256.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    data = payload["data_json"].encode("utf-8")
    tags = [
        {"name": b64url(t["name"].encode()), "value": b64url(t["value"].encode())}
        for t in payload["tags"]
    ]
    owner = wallet["n"]
    data_root = compute_data_root(data)
    tx: dict[str, Any] = {
        "format": 2,
        "id": "",
        "last_tx": last_tx,
        "owner": owner,
        "tags": tags,
        "target": "",
        "quantity": "0",
        "data": b64url(data),
        "data_size": str(len(data)),
        "data_root": b64url(data_root),
        "reward": reward,
        "signature": "",
    }

    tag_list = [
        [b64url_decode(t["name"]), b64url_decode(t["value"])] for t in tags
    ]
    sig_data = deep_hash([
        b"2",
        b64url_decode(owner),
        b"",
        b"0",
        reward.encode(),
        b64url_decode(last_tx),
        tag_list,
        str(len(data)).encode(),
        data_root,
    ])

    private_numbers = rsa.RSAPrivateNumbers(
        p=int.from_bytes(b64url_decode(wallet["p"]), "big"),
        q=int.from_bytes(b64url_decode(wallet["q"]), "big"),
        d=int.from_bytes(b64url_decode(wallet["d"]), "big"),
        dmp1=int.from_bytes(b64url_decode(wallet["dp"]), "big"),
        dmq1=int.from_bytes(b64url_decode(wallet["dq"]), "big"),
        iqmp=int.from_bytes(b64url_decode(wallet["qi"]), "big"),
        public_numbers=rsa.RSAPublicNumbers(
            e=int.from_bytes(b64url_decode(wallet["e"]), "big"),
            n=int.from_bytes(b64url_decode(wallet["n"]), "big"),
        ),
    )
    private_key = private_numbers.private_key()
    signature = private_key.sign(
        sig_data,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
        hashes.SHA256(),
    )
    tx["signature"] = b64url(signature)
    tx["id"] = b64url(hashlib.sha256(signature).digest())
    return tx


def upload_payload(
    payload: dict[str, Any],
    wallet_path: str | Path | None = None,
    gateway: str = ARWEAVE_GATEWAY,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Sign + POST one payload to Arweave. Returns gateway response info.

    Requires a wallet JWK file (``wallet_path`` or ``ARWEAVE_WALLET``
    env var). Raises if no wallet is available — this function never
    spends anything on its own and never creates a wallet. Payloads we
    produce are < 256 KiB, so the transaction JSON (with inline data)
    is accepted by the gateway directly.
    """
    wallet_path = wallet_path or os.environ.get("ARWEAVE_WALLET")
    if not wallet_path:
        raise RuntimeError(
            "No Arweave wallet supplied. Pass --wallet path/to/wallet.json or set "
            "ARWEAVE_WALLET. Use --dry-run to build the payload without uploading."
        )
    wallet = _load_wallet(wallet_path)
    with httpx.Client(timeout=timeout) as client:
        reward = client.get(f"{gateway}/price/{len(payload['data_json'])}").text.strip()
        last_tx = client.get(f"{gateway}/tx_anchor").text.strip()
        tx = build_transaction(payload, wallet, reward, last_tx)
        resp = client.post(f"{gateway}/tx", json=tx)
        resp.raise_for_status()
    return {
        "tx_id": tx["id"],
        "arweave_url": f"https://arweave.net/{tx['id']}",
        "reward_winston": reward,
    }
