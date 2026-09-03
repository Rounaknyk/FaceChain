from __future__ import annotations

import argparse
import json
import os
import time
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


def run(image_path: Path | None, artifacts: Path, dry_run: bool = False) -> None:
    if not image_path:
        print("Choose input method:")
        print("1) Webcam")
        print("2) Browse File")
        choice = input("Enter 1 or 2: ").strip()
        if choice == "2":
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            file_path = filedialog.askopenfilename(
                title="Select Image",
                filetypes=[("Image Files", "*.jpg *.jpeg *.png")]
            )
            if not file_path:
                raise SystemExit("No file selected.")
            image_path = Path(file_path)

    import cv2
    import numpy as np
    
    if image_path:
        original_image = image_path.read_bytes()
        img_arr = np.frombuffer(original_image, np.uint8)
        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        if img is None:
            raise SystemExit(f"Error: Failed to load image from {image_path}")
    else:
        print("Capturing image from webcam...")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise SystemExit("Error: Could not open webcam.")
        time.sleep(2)  # Allow camera sensor to warm up
        ret, img = cap.read()
        cap.release()
        if not ret:
            raise SystemExit("Error: Failed to capture frame from webcam.")
            
        # Encode webcam frame losslessly to act as the "original" high-fidelity image
        is_success, buffer = cv2.imencode(".png", img)
        if not is_success:
            raise SystemExit("Error: Failed to encode webcam frame.")
        original_image = buffer.tobytes()
            
    # Resize and compress image specifically for Face++ (prevent 413 Request Entity Too Large errors)
    max_dim = 1024
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        facepp_img = cv2.resize(img, (int(w * scale), int(h * scale)))
    else:
        facepp_img = img
        
    is_success, buffer = cv2.imencode(".jpg", facepp_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not is_success:
        raise SystemExit("Error: Failed to encode image to JPEG for Face++.")
    facepp_image = buffer.tobytes()
    
    print("Image inputted...")
    print("Encoding face...")
    face = detect_face(facepp_image, required_env("FACEPP_API_KEY"), required_env("FACEPP_API_SECRET"))
    print("Face encoded.")
    
    # Draw face bounding box and landmarks
    viz_img = facepp_img.copy()
    rect = face.get("face_rectangle", {})
    if rect:
        x, y = rect.get("left", 0), rect.get("top", 0)
        w, h = rect.get("width", 0), rect.get("height", 0)
        cv2.rectangle(viz_img, (x, y), (x+w, y+h), (0, 255, 0), 2)
    landmarks = face.get("landmark", {})
    for point in landmarks.values():
        cv2.circle(viz_img, (point.get("x", 0), point.get("y", 0)), 2, (0, 0, 255), -1)

    print("Reversing image search...")
    web = reverse_image_search(original_image, required_env("GOOGLE_VISION_API_KEY"))
    match = choose_social_match(web)
    print(f"Found this on social: {match['url']}")

    print("Building privacy-preserving evidence...")
    evidence = build_evidence(original_image, face, match)
    path, digest = write_artifact(evidence, artifacts)
    
    viz_path = artifacts / f"landmarks-{digest[:12]}.jpg"
    cv2.imwrite(str(viz_path), viz_img)
    print(f"Evidence SHA-256: {digest}")
    print(f"Landmark visualization saved to {viz_path}")

    if dry_run:
        print("DRY RUN: blockchain broadcast skipped.")
        print(f"Unsigned evidence written to {path}")
        return

    print("Committing evidence to Ethereum Sepolia...")
    chain = commit_hash(digest, required_env("SEPOLIA_RPC_URL"), required_env("SEPOLIA_PRIVATE_KEY"))
    final = {**evidence, "commitment": chain}
    path.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
    print(f"Transaction hash: {chain['transaction_hash']}")
    print(f"Evidence written to {path}")


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
    run_parser.add_argument("image", type=Path, nargs="?", help="optional path to image file (omit to use interactive prompt)")
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
