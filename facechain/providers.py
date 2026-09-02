from __future__ import annotations

import base64

import requests


class ProviderError(RuntimeError):
    pass


def _error_message(payload: dict, fallback: str) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message", error))
    return str(error or payload.get("error_message") or fallback)


def detect_face(image: bytes, api_key: str, api_secret: str) -> dict:
    response = requests.post(
        "https://api-us.faceplusplus.com/facepp/v3/detect",
        data={
            "api_key": api_key,
            "api_secret": api_secret,
            "return_landmark": "1",
            "return_attributes": "none",
        },
        files={"image_file": ("input.jpg", image)},
        timeout=45,
    )
    payload = response.json()
    if not response.ok or payload.get("error_message"):
        raise ProviderError(f"Face++ failed: {_error_message(payload, response.text)}")
    faces = payload.get("faces", [])
    if len(faces) != 1:
        raise ProviderError(f"Expected exactly one face, detected {len(faces)}")
    return faces[0]


def reverse_image_search(image: bytes, api_key: str) -> dict:
    response = requests.post(
        f"https://vision.googleapis.com/v1/images:annotate?key={api_key}",
        json={
            "requests": [{
                "image": {"content": base64.b64encode(image).decode()},
                "features": [{"type": "WEB_DETECTION", "maxResults": 30}],
            }]
        },
        timeout=60,
    )
    payload = response.json()
    if not response.ok or payload.get("error"):
        message = _error_message(payload, response.text)
        if "requires billing to be enabled" in message:
            message += " Enable billing in Google Cloud Console, then wait a few minutes and retry."
        raise ProviderError(f"Google Vision failed: {message}")
    result = payload["responses"][0]
    if result.get("error"):
        raise ProviderError(f"Google Vision failed: {result['error']}")
    return result.get("webDetection", {})
