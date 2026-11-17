"""PermaInfer CLI: verify a ledger, build Arweave payloads, upload them.

Usage:
    permainfer verify [--ledger data/ledger.jsonl]
    permainfer arweave-payload [--ledger ...] [--receipt <id> | --bundle]
                               [--out payload.json]
    permainfer arweave-upload [--ledger ...] --wallet wallet.json [--bundle]
    permainfer serve [--host 0.0.0.0] [--port 8000]

``verify`` and ``arweave-payload`` are offline and free. ``arweave-upload``
needs a funded Arweave wallet (user step) and spends a small amount of AR.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import arweave as arweave_mod
from .receipts import ReceiptLedger


def cmd_verify(args) -> int:
    ledger = ReceiptLedger(args.ledger)
    ok, problems = ledger.verify()
    print(f"ledger: {args.ledger}  entries: {len(ledger)}")
    if ok:
        print("OK — receipt chain intact, all hashes match.")
        return 0
    print("BROKEN — problems:")
    for p in problems:
        print(f"  - {p}")
    return 1


def cmd_arweave_payload(args) -> int:
    ledger = ReceiptLedger(args.ledger)
    receipts = ledger.load_all()
    if args.receipt:
        matches = [r for r in receipts if r.receipt_id == args.receipt]
        if not matches:
            print(f"receipt not found: {args.receipt}", file=sys.stderr)
            return 1
        payload = arweave_mod.receipt_to_arweave_payload(matches[0])
    else:
        payload = arweave_mod.ledger_to_arweave_payload(receipts)
    out = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"wrote {args.out} ({len(payload['data_json'])} bytes of data, "
              f"{len(payload['tags'])} tags)")
        print("Dry-run payload only — nothing uploaded, nothing spent.")
    else:
        print(out)
        print("Dry-run payload only — nothing uploaded, nothing spent.", file=sys.stderr)
    return 0


def cmd_arweave_upload(args) -> int:
    ledger = ReceiptLedger(args.ledger)
    receipts = ledger.load_all()
    payload = arweave_mod.ledger_to_arweave_payload(receipts)
    print(f"Uploading bundle of {len(receipts)} receipts "
          f"({len(payload['data_json'])} bytes)...")
    try:
        result = arweave_mod.upload_payload(payload, wallet_path=args.wallet)
    except Exception as exc:  # noqa: BLE001 - CLI surfaces the error
        print(f"upload failed: {exc}", file=sys.stderr)
        return 1
    print(f"Uploaded: {result['arweave_url']}")
    print(f"tx id: {result['tx_id']}  reward: {result['reward_winston']} winston")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="permainfer", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("verify", help="Verify the receipt chain of a ledger")
    p.add_argument("--ledger", default="data/ledger.jsonl")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("arweave-payload", help="Build an Arweave payload (offline, free)")
    p.add_argument("--ledger", default="data/ledger.jsonl")
    p.add_argument("--receipt", help="single receipt id (default: whole ledger bundle)")
    p.add_argument("--out", help="write payload JSON to this file")
    p.set_defaults(func=cmd_arweave_payload)

    p = sub.add_parser("arweave-upload", help="Upload the ledger bundle to Arweave (costs AR)")
    p.add_argument("--ledger", default="data/ledger.jsonl")
    p.add_argument("--wallet", required=True, help="Arweave wallet JWK JSON file")
    p.set_defaults(func=cmd_arweave_upload)

    p = sub.add_parser("serve", help="Run the inference server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=lambda a: _serve(a))

    args = parser.parse_args(argv)
    return args.func(args)


def _serve(args) -> int:
    import uvicorn

    uvicorn.run(
        "permainfer.server:create_app_factory",
        host=args.host,
        port=args.port,
        factory=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
