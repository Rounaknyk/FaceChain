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
from rich.console import Console
from rich.panel import Panel

console = Console()


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing {name}; copy .env.example to .env and fill it in")
    return value


def run(image_path: Path | None, artifacts: Path, dry_run: bool = False) -> None:
    console.rule("[bold cyan]🔍 Case Opened: FaceChain Identity Verification[/bold cyan]")
    
    if not image_path:
        console.print("[bold yellow]Choose input method:[/bold yellow]")
        console.print("  [1] 📷 Webcam")
        console.print("  [2] 📁 Browse File")
        choice = console.input("[bold cyan]Enter 1 or 2: [/bold cyan]").strip()
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
        with console.status("[bold blue]Loading image file...[/bold blue]"):
            original_image = image_path.read_bytes()
            img_arr = np.frombuffer(original_image, np.uint8)
            img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
            if img is None:
                console.print(f"[bold red]Error: Failed to load image from {image_path}[/bold red]")
                raise SystemExit(1)
        console.print("[green]✓[/green] Image loaded from file")
    else:
        with console.status("[bold blue]📷 Initializing webcam...[/bold blue]"):
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                console.print("[bold red]Error: Could not open webcam.[/bold red]")
                raise SystemExit(1)
            time.sleep(2)  # Allow camera sensor to warm up
            ret, img = cap.read()
            cap.release()
            if not ret:
                console.print("[bold red]Error: Failed to capture frame from webcam.[/bold red]")
                raise SystemExit(1)
                
            # Encode webcam frame losslessly to act as the "original" high-fidelity image
            is_success, buffer = cv2.imencode(".png", img)
            if not is_success:
                console.print("[bold red]Error: Failed to encode webcam frame.[/bold red]")
                raise SystemExit(1)
            original_image = buffer.tobytes()
        console.print("[green]✓[/green] Image captured from webcam")
            
    with console.status("[bold blue]⚙️ Preprocessing image for Face++...[/bold blue]"):
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
            console.print("[bold red]Error: Failed to encode image to JPEG for Face++.[/bold red]")
            raise SystemExit(1)
        facepp_image = buffer.tobytes()
    
    with console.status("[bold blue]👤 Extracting biometric signature via Face++...[/bold blue]"):
        face = detect_face(facepp_image, required_env("FACEPP_API_KEY"), required_env("FACEPP_API_SECRET"))
        
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
    console.print(f"[green]✓[/green] Face encoded ({len(landmarks)} landmarks detected)")

    with console.status("[bold blue]🕵️ Cross-referencing global web index (Google Vision)...[/bold blue]"):
        web = reverse_image_search(original_image, required_env("GOOGLE_VISION_API_KEY"))
        match = choose_social_match(web)
    console.print(f"[green]✓[/green] Found indexed match on social media: [bold cyan]{match['url']}[/bold cyan]")

    with console.status("[bold blue]⛓️ Filing tamper-proof record...[/bold blue]"):
        evidence = build_evidence(original_image, face, match)
        path, digest = write_artifact(evidence, artifacts)
        
        viz_path = artifacts / f"landmarks-{digest[:12]}.jpg"
        cv2.imwrite(str(viz_path), viz_img)
    console.print("[green]✓[/green] Evidence JSON and landmark visualization built")
    console.print(f"    [dim]Evidence SHA-256: {digest}[/dim]")
    console.print(f"    [dim]Landmark image: {viz_path}[/dim]")

    if dry_run:
        console.rule("[bold yellow]DRY RUN COMPLETE[/bold yellow]")
        console.print("[yellow]Blockchain broadcast skipped; no SepoliaETH spent.[/yellow]")
        console.print(f"Unsigned evidence written to [bold]{path}[/bold]")
        return

    with console.status("[bold blue]🚀 Anchoring evidence to Ethereum Sepolia...[/bold blue]"):
        chain = commit_hash(digest, required_env("SEPOLIA_RPC_URL"), required_env("SEPOLIA_PRIVATE_KEY"))
        final = {**evidence, "commitment": chain}
        path.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
        
    console.rule("[bold green]CASE CLOSED & VERIFIED[/bold green]")
    console.print(f"    [bold]Transaction hash:[/bold] {chain['transaction_hash']}")
    console.print(f"    [bold]Etherscan Explorer:[/bold] [link={chain['explorer_url']}]{chain['explorer_url']}[/link]")
    console.print(f"    [bold]Evidence file:[/bold] {path}")


def verify(path: Path) -> None:
    console.rule("[bold cyan]🔍 Verifying FaceChain Evidence[/bold cyan]")
    document = json.loads(path.read_text())
    chain = document.pop("commitment")
    digest = evidence_hash(document)
    
    with console.status("[bold blue]📡 Fetching transaction from Ethereum Sepolia...[/bold blue]"):
        result = verify_hash(digest, chain["transaction_hash"], required_env("SEPOLIA_RPC_URL"))
        
    console.print(f"  [bold]Computed SHA-256:[/bold] {digest}")
    console.print(f"  [bold]Transaction Input:[/bold] {result.get('on_chain_hash', 'N/A')}")
    
    if result["valid"]:
        console.print(Panel("[bold green]VERIFICATION SUCCESSFUL[/bold green]\nThe evidence perfectly matches the immutable blockchain record.", expand=False))
    else:
        console.print(Panel(f"[bold red]VERIFICATION FAILED[/bold red]\n{result.get('error', 'Hash mismatch')}", expand=False))
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
        console.print(f"\n[bold red]ERROR:[/bold red] {error}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
