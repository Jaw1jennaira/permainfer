"""Tests for PermaInfer receipts, Arweave payloads, and the HTTP API.

Run:  pytest -q
These tests use only the EchoBackend (no model download, no network,
no wallet) — they exercise the verifiability layer, which is the part
that must be right no matter where the compute runs.
"""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from permainfer import arweave as ar_mod
from permainfer.model import EchoBackend, GenerationParams
from permainfer.receipts import ReceiptLedger, build_receipt, canonical_json, sha256_hex
from permainfer.server import create_app

NODE = "test-node"


def _receipt(prev="", prompt="hello", completion="world"):
    return build_receipt(
        prev_receipt_id=prev,
        model="echo/0.1",
        model_file="echo",
        model_sha256=EchoBackend.model_sha256,
        prompt=prompt,
        completion=completion,
        params={"temperature": 0.7, "max_tokens": 16, "top_p": 0.9, "stop": []},
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "wall_seconds": 0.0},
        node=NODE,
        created_at=1780000000.0,
    )


# --- receipts ---------------------------------------------------------------

def test_receipt_id_is_hash_of_canonical_body():
    r = _receipt()
    assert r.receipt_id == sha256_hex(canonical_json(r.body()))
    assert r.prompt_sha256 == hashlib.sha256(b"hello").hexdigest()
    assert r.completion_sha256 == hashlib.sha256(b"world").hexdigest()


def test_receipt_ids_are_deterministic():
    assert _receipt().receipt_id == _receipt().receipt_id


def test_ledger_chain_and_verify(tmp_path):
    ledger = ReceiptLedger(tmp_path / "ledger.jsonl")
    r1 = _receipt(prev="")
    r2 = _receipt(prev=r1.receipt_id, prompt="second", completion="answer")
    ledger.append(r1)
    ledger.append(r2)
    assert len(ledger) == 2
    ok, problems = ledger.verify()
    assert ok and problems == []


def test_ledger_rejects_wrong_prev(tmp_path):
    ledger = ReceiptLedger(tmp_path / "ledger.jsonl")
    ledger.append(_receipt(prev=""))
    with pytest.raises(ValueError):
        ledger.append(_receipt(prev="not-the-tip"))


def test_ledger_detects_tampering(tmp_path):
    ledger = ReceiptLedger(tmp_path / "ledger.jsonl")
    ledger.append(_receipt(prev=""))
    ledger.append(_receipt(prev=ledger.last_receipt_id(), prompt="b", completion="c"))
    # Tamper: rewrite the first line with an altered completion hash.
    lines = (tmp_path / "ledger.jsonl").read_text().splitlines()
    first = json.loads(lines[0])
    first["completion_sha256"] = "0" * 64
    lines[0] = json.dumps(first, sort_keys=True)
    (tmp_path / "ledger.jsonl").write_text("\n".join(lines) + "\n")
    ok, problems = ledger.verify()
    assert not ok
    assert any("hash mismatch" in p for p in problems)


# --- arweave payloads --------------------------------------------------------

def test_arweave_payload_is_offline_and_complete():
    r = _receipt()
    payload = ar_mod.receipt_to_arweave_payload(r)
    assert payload["data"]["receipt_id"] == r.receipt_id
    tags = {t["name"]: t["value"] for t in payload["tags"]}
    assert tags["App-Name"] == "PermaInfer"
    assert tags["Receipt-ID"] == r.receipt_id
    assert tags["Model-SHA256"] == r.model_sha256
    assert json.loads(payload["data_json"])["receipt_id"] == r.receipt_id


def test_ledger_bundle_payload():
    receipts = [_receipt(prev=""), _receipt(prev="x", prompt="b", completion="c")]
    receipts[1].prev_receipt_id = receipts[0].receipt_id
    payload = ar_mod.ledger_to_arweave_payload(receipts)
    assert payload["data"]["count"] == 2
    assert payload["data"]["tip_receipt_id"] == receipts[1].receipt_id


def test_deep_hash_is_deterministic_and_tagged():
    h1 = ar_mod.deep_hash([b"2", b"owner", [b"name", b"value"]])
    h2 = ar_mod.deep_hash([b"2", b"owner", [b"name", b"value"]])
    assert h1 == h2 and len(h1) == 48  # SHA-384
    assert ar_mod.deep_hash(b"abc") != ar_mod.deep_hash(b"abd")
    assert ar_mod.deep_hash(b"abc") != ar_mod.deep_hash([b"abc"])


def test_data_root_single_chunk_matches_spec():
    data = b"hello perma-infer"
    root = ar_mod.compute_data_root(data)
    # Spec (arweave-js merkle.ts): leaf = SHA256(SHA256(SHA256(data))
    #   || SHA256(len as 32-byte BE)); single chunk => root = leaf.
    leaf = hashlib.sha256(
        hashlib.sha256(hashlib.sha256(data).digest()).digest()
        + hashlib.sha256(len(data).to_bytes(32, "big")).digest()
    ).digest()
    assert root == leaf
    assert len(root) == 32


def test_build_transaction_is_deterministic_without_signature_randomness():
    # RSA-PSS is randomized, so two signatures differ — but the tx
    # structure, data_root and id derivation must be well-formed.
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.private_numbers()
    pub = numbers.public_numbers

    def b64u(n: int) -> str:
        b = n.to_bytes((n.bit_length() + 7) // 8, "big")
        import base64
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    wallet = {
        "kty": "RSA", "e": b64u(pub.e), "n": b64u(pub.n),
        "d": b64u(numbers.d), "p": b64u(numbers.p), "q": b64u(numbers.q),
        "dp": b64u(numbers.dmp1), "dq": b64u(numbers.dmq1), "qi": b64u(numbers.iqmp),
    }
    payload = ar_mod.receipt_to_arweave_payload(_receipt())
    tx = ar_mod.build_transaction(payload, wallet, reward="12345", last_tx="a" * 43)
    assert tx["format"] == 2
    assert tx["data_size"] == str(len(payload["data_json"]))
    assert tx["id"] == ar_mod.b64url(hashlib.sha256(ar_mod.b64url_decode(tx["signature"])).digest())
    # data_root must match the merkle root of the payload bytes
    assert ar_mod.b64url_decode(tx["data_root"]) == ar_mod.compute_data_root(
        payload["data_json"].encode()
    )
    # Verify the signature with the public key over the deep-hashed data.
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    tag_list = [[ar_mod.b64url_decode(t["name"]), ar_mod.b64url_decode(t["value"])] for t in tx["tags"]]
    sig_data = ar_mod.deep_hash([
        b"2", ar_mod.b64url_decode(tx["owner"]), b"", b"0",
        tx["reward"].encode(), ar_mod.b64url_decode(tx["last_tx"]),
        tag_list, tx["data_size"].encode(), ar_mod.b64url_decode(tx["data_root"]),
    ])
    pub_key = pub.public_key()
    pub_key.verify(
        ar_mod.b64url_decode(tx["signature"]), sig_data,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
        hashes.SHA256(),
    )  # raises if invalid


# --- HTTP API (echo backend) --------------------------------------------------

@pytest.fixture()
def client(tmp_path):
    app = create_app(backend=EchoBackend(), ledger_path=tmp_path / "ledger.jsonl")
    with TestClient(app) as c:
        yield c


def test_health_and_models(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/v1/models").json()["data"][0]["id"] == "echo/0.1"


def test_chat_completion_mints_receipt(client):
    resp = client.post("/v1/chat/completions", json={
        "model": "echo/0.1",
        "messages": [{"role": "user", "content": "What is 2+2?"}],
        "max_tokens": 32,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["choices"][0]["message"]["content"].startswith("[echo]")
    receipt_id = body["permainfer_receipt"]["receipt_id"]
    got = client.get(f"/receipts/{receipt_id}")
    assert got.status_code == 200
    assert got.json()["prompt_sha256"] == hashlib.sha256(
        b"user: What is 2+2?").hexdigest()
    assert client.get("/ledger/verify").json()["ok"] is True


def test_receipt_arweave_payload_endpoint(client):
    client.post("/v1/chat/completions", json={
        "model": "echo/0.1",
        "messages": [{"role": "user", "content": "hi"}],
    })
    receipts = client.get("/receipts").json()["receipts"]
    rid = receipts[0]["receipt_id"]
    payload = client.get(f"/receipts/{rid}/arweave").json()
    assert payload["data"]["receipt_id"] == rid
    assert any(t["name"] == "App-Name" and t["value"] == "PermaInfer" for t in payload["tags"])


def test_ledger_arweave_dry_run(client):
    client.post("/v1/chat/completions", json={
        "model": "echo/0.1",
        "messages": [{"role": "user", "content": "hi"}],
    })
    resp = client.post("/ledger/arweave", json={"dry_run": True})
    assert resp.status_code == 200
    assert resp.json()["dry_run"] is True
    assert resp.json()["receipt_count"] == 1


def test_unknown_model_rejected(client):
    resp = client.post("/v1/chat/completions", json={
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert resp.status_code == 404
