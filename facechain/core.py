from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


SOCIAL_HOSTS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "pinterest.com",
    "reddit.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtube.com",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def evidence_hash(evidence: dict) -> str:
    return sha256_bytes(canonical_json(evidence))


def host_for(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def is_social_url(url: str) -> bool:
    host = host_for(url)
    return any(host == allowed or host.endswith("." + allowed) for allowed in SOCIAL_HOSTS)


def choose_social_match(web_detection: dict) -> dict:
    """Choose a social page returned by Google's exact/partial match index."""
    pages = web_detection.get("pagesWithMatchingImages", [])
    for page in pages:
        url = page.get("url", "")
        if is_social_url(url):
            return {
                "url": url,
                "page_title": page.get("pageTitle"),
                "domain": host_for(url),
                "match_basis": "Google Vision pagesWithMatchingImages",
            }
    raise LookupError(
        "Reverse search found no indexed social-media page. Try an image already posted publicly."
    )


def normalized_landmark_encoding(face: dict) -> list[float]:
    """Encode ordered landmarks relative to the detected face rectangle."""
    rectangle = face["face_rectangle"]
    width = max(rectangle["width"], 1)
    height = max(rectangle["height"], 1)
    left = rectangle["left"]
    top = rectangle["top"]
    vector: list[float] = []
    for name in sorted(face.get("landmark", {})):
        point = face["landmark"][name]
        vector.extend([
            round((point["x"] - left) / width, 6),
            round((point["y"] - top) / height, 6),
        ])
    return vector


def build_evidence(image: bytes, face: dict, reverse_match: dict) -> dict:
    # Do not put a biometric template, API secret, or original image in this document.
    encoding = normalized_landmark_encoding(face)
    return {
        "schema": "facechain-evidence-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_image_sha256": sha256_bytes(image),
        "face": {
            "provider": "Face++ Detect API",
            "face_token_sha256": sha256_bytes(face["face_token"].encode()),
            "rectangle": face["face_rectangle"],
            "encoding": "normalized-landmark-vector-v1",
            "encoding_dimensions": len(encoding),
            "encoding_sha256": sha256_bytes(canonical_json({"vector": encoding})),
        },
        "reverse_image_search": {
            "provider": "Google Cloud Vision Web Detection",
            **reverse_match,
        },
    }


def write_artifact(evidence: dict, directory: Path) -> tuple[Path, str]:
    digest = evidence_hash(evidence)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"evidence-{digest[:12]}.json"
    path.write_bytes(canonical_json(evidence) + b"\n")
    return path, digest
