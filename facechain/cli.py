from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .chain import commit_hash, verify_hash
from .core import build_evidence, choose_social_match, evidence_hash, write_artifact
from .providers import ProviderError, detect_face, reverse_image_search


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing {name}; copy .env.example to .env and fill it in")
    return value


def run(image_path: Path, artifacts: Path, dry_run: bool = False) -> None:
    image = image_path.read_bytes()
    print("[1/4] Detecting and encoding one face with Face++...")
    face = detect_face(image, required_env("FACEPP_API_KEY"), required_env("FACEPP_API_SECRET"))
    print(f"      face detected; {len(face.get('landmark', {}))} landmarks encoded")

    print("[2/4] Running genuine Google reverse-image search...")
    web = reverse_image_search(image, required_env("GOOGLE_VISION_API_KEY"))
    match = choose_social_match(web)
    print(f"      indexed match: {match['url']}")

    print("[3/4] Building privacy-preserving evidence...")
    evidence = build_evidence(image, face, match)
    path, digest = write_artifact(evidence, artifacts)
    print(f"      SHA-256: {digest}")

    if dry_run:
        print("[4/4] DRY RUN: blockchain broadcast skipped; no SepoliaETH spent")
        print(f"\nUnsigned evidence written to {path}")
        return

    print("[4/4] Committing evidence hash to Ethereum Sepolia...")
    chain = commit_hash(digest, required_env("SEPOLIA_RPC_URL"), required_env("SEPOLIA_PRIVATE_KEY"))
    final = {**evidence, "commitment": chain}
    path.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
    print(f"      transaction: {chain['transaction_hash']}")
    print(f"      explorer: {chain['explorer_url']}")
    print(f"\nEvidence written to {path}")


def verify(path: Path) -> None:
    document = json.loads(path.read_text())
    chain = document.pop("commitment")
    digest = evidence_hash(document)
    result = verify_hash(digest, chain["transaction_hash"], required_env("SEPOLIA_RPC_URL"))
    print(json.dumps({"evidence_sha256": digest, **result}, indent=2))
    if not result["valid"]:
        raise SystemExit(1)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="facechain")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="run the full verification pipeline")
    run_parser.add_argument("image", type=Path)
    run_parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run face search and evidence hashing without a blockchain transaction",
    )
    verify_parser = sub.add_parser("verify", help="verify an evidence file against Sepolia")
    verify_parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    try:
        run(args.image, args.artifacts, args.dry_run) if args.command == "run" else verify(args.evidence)
    except (ProviderError, LookupError, FileNotFoundError, ConnectionError) as error:
        raise SystemExit(f"\nERROR: {error}") from None


if __name__ == "__main__":
    main()
