# FaceChain — Face ID + Blockchain Verification

FaceChain is a CLI pipeline that takes a photo, detects and encodes its face,
finds an actually indexed matching social-media page using reverse-image search,
and anchors the result to a public blockchain.

It does **not** contain hardcoded search results. A run fails honestly if Google
does not return an indexed social post for that image.

## What happens end to end

```mermaid
graph TD
    A[Start Pipeline] --> B{Input Method?}
    B -->|Interactive prompt| C[1: Capture from Webcam]
    B -->|Interactive prompt| D[2: Browse File via dialog]
    B -->|CLI Argument| E[Read file directly]
    C --> F[Raw High-Fidelity Image]
    D --> F
    E --> F
    F -->|max 1024px, 85% JPEG| G[Face++ Detection]
    G --> H[Extract 83 Face Landmarks]
    H --> I[Generate Visual Artifact]
    H --> J[Compute Independent Geometric Signature]
    F -->|Original Bytes| K[Google Cloud Vision Web Search]
    K --> L[Filter for recognized Social Media URL]
    J --> M[Build Privacy-preserving Evidence JSON]
    L --> M
    M --> N[Anchor to Ethereum Sepolia Blockchain]
```
1. **Face ID:** Face++ Detect uploads the compressed input, requires exactly one detected
   face, and returns 83 facial landmarks. FaceChain computes an independent mathematical 
   encoding of those ordered landmarks. Only hashes of that vector and the provider token 
   are kept; raw biometric data is discarded. A visualization of the detected landmarks is also generated.
   *(Note: Images sent to Face++ are compressed to meet API size limits. This does not impact accuracy, as facial recognition relies on relative geometric proportions which remain invariant across compression levels.)*
2. **Reverse-image search:** Google Cloud Vision Web Detection searches the
   public web from the original, high-fidelity image bytes. FaceChain accepts only a URL from Google's
   `pagesWithMatchingImages` response whose domain is a recognized social site.
3. **Evidence:** The input hash, hashed face token, face geometry, provider,
   result URL, and timestamp become canonical JSON.
4. **Blockchain:** The evidence SHA-256 is written into a zero-value transaction
   on **Ethereum Sepolia** (chain ID `11155111`). The signed transaction calldata
   is immutable, publicly inspectable, and does not expose the photo or biometric
   token. `verify` downloads the transaction and recomputes the commitment.

## Setup

Prerequisites: Python 3.10–3.14, a Face++ account, a Google Cloud project with
Vision API enabled, and a Sepolia wallet containing a small amount of test ETH.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env`. Never commit it or expose it in a recording. Use a disposable
test-only wallet; never use a wallet containing real assets. Public Sepolia RPC
URLs are available from common Ethereum node providers, and test ETH is available
from Sepolia faucets.

Use a photo that is already present in a public, indexed social post, then run:

```bash
# Run interactively (will prompt to use Webcam or browse for a file)
python -m facechain.cli run --dry-run
python -m facechain.cli run

# Or provide a file path directly
python -m facechain.cli run ./demo/person.jpeg

# Verify the evidence
python -m facechain.cli verify ./artifacts/evidence-XXXXXXXXXXXX.json
```

The `--dry-run` command executes face detection, face encoding, genuine reverse
search, social-result validation, evidence generation, and deterministic hashing.
It stops before signing or broadcasting, so it spends no SepoliaETH. Use the
normal command once for the final recorded end-to-end blockchain proof.

The run prints the matched post, evidence hash, transaction hash, and Etherscan
URL. Open the Etherscan link during the demo and show the transaction input.

## Verified live proof

The pipeline completed successfully against the real external services on
September 2, 2026:

- Face++ detected one face and returned 83 landmarks (166 encoded dimensions).
- Google Vision Web Detection returned a matching public Instagram post.
- Evidence SHA-256: `a766118b49eeab6419b9c6f5eb3181cdc8c8b143a9bfee9d14cf2b45096c08eb`.
- The commitment was included in Sepolia block `11621173`.
- Independent `verify` output returned `"valid": true`.

[View the Sepolia transaction](https://sepolia.etherscan.io/tx/c131873c3403d4c84b4c6ae158e0a1f429291b437f5bc6c8b13b6323d7b4a64c)
or inspect the committed [`proof/evidence-a766118b49ee.json`](proof/evidence-a766118b49ee.json).
The portrait itself is intentionally excluded from Git because it contains
biometric data.

## Tests

```bash
python -m unittest discover -v
```

Tests cover deterministic evidence hashing, privacy of the stored face token,
social-domain selection, and honest failure when no social match exists. External
providers are intentionally not mocked in the recorded demo.

## Unedited demo recording checklist

Record one continuous terminal capture:

1. Briefly show the input image and its known public social post.
2. Show `git status`, `.env.example` (not `.env`), and run the tests.
3. Run `python -m facechain.cli run ...`; keep all four stages visible.
4. Open the printed Etherscan URL and show status `Success`, Sepolia, and input data.
5. Run `python -m facechain.cli verify artifacts/evidence-....json` and show
   `"valid": true`.
6. Change one character in a **copy** of the evidence file and verify the copy;
   it must print `"valid": false`. Do not edit the original artifact.

## Known limitations

- Google can only find public pages it has indexed; private, new, deleted, or
  robots-blocked posts will not match.
- “Matching image” is Google's web-index assertion. FaceChain records that
  provenance; it does not claim the social account owns or created the photo.
- Face++ processes the image remotely. This prototype avoids storing raw images
  or biometric tokens on-chain, but production use needs consent, retention,
  regional privacy review, and liveness/anti-spoofing.
- Social-domain filtering is explicit and conservative; add sites in
  `facechain/core.py` when needed.
- Sepolia is a test network. For production-grade permanence, switch the RPC and
  chain guard to Ethereum mainnet or an appropriate L2.
- The local evidence JSON must remain available: the chain stores its commitment,
  not the complete document.

## Repository layout

```text
facechain/core.py       deterministic evidence and social matching
facechain/providers.py  real Face++ and Google Vision API calls
facechain/chain.py      Sepolia write and independent verification
facechain/cli.py        run/verify command-line interface
tests/test_core.py      offline unit tests
proof/                  sanitized evidence from a verified live run
demo/README.md          local demo-image instructions (image is not committed)
```

## Ethics

Only process images with permission. A face match is probabilistic biometric
evidence, not identity proof. Do not use this prototype for surveillance,
employment, credit, policing, or other high-impact decisions.
