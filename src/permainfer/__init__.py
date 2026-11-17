"""PermaInfer — verifiable open-weight inference with permanent receipts.

Public API surface of the package. The server is the entry point; the
receipts module is the verifiability layer; the arweave module turns a
receipt into a permanent, Arweave-ready transaction payload.
"""

from .receipts import Receipt, ReceiptLedger, build_receipt, canonical_json, sha256_hex

__all__ = [
    "Receipt",
    "ReceiptLedger",
    "build_receipt",
    "canonical_json",
    "sha256_hex",
]
