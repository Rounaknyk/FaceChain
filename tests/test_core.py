import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from facechain.cli import run
from facechain.core import build_evidence, choose_social_match, evidence_hash, write_artifact


class CoreTests(unittest.TestCase):
    def test_selects_real_social_result_not_first_arbitrary_page(self):
        web = {"pagesWithMatchingImages": [
            {"url": "https://news.example/photo"},
            {"url": "https://www.instagram.com/p/real-post", "pageTitle": "Post"},
        ]}
        self.assertEqual(choose_social_match(web)["domain"], "instagram.com")

    def test_rejects_no_social_match(self):
        with self.assertRaises(LookupError):
            choose_social_match({"pagesWithMatchingImages": [{"url": "https://example.com/x"}]})

    def test_artifact_digest_is_reproducible(self):
        evidence = build_evidence(
            b"photo",
            {
                "face_token": "secret-template",
                "face_rectangle": {"top": 0, "left": 0, "width": 100, "height": 100},
                "landmark": {"nose": {"x": 50, "y": 40}},
            },
            {"url": "https://x.com/a/status/1", "domain": "x.com", "match_basis": "test"},
        )
        self.assertNotIn("secret-template", json.dumps(evidence))
        self.assertEqual(evidence["face"]["encoding_dimensions"], 2)
        with TemporaryDirectory() as directory:
            path, digest = write_artifact(evidence, Path(directory))
            self.assertEqual(evidence_hash(json.loads(path.read_text())), digest)

    def test_dry_run_never_calls_blockchain(self):
        face = {
            "face_token": "template",
            "face_rectangle": {"top": 0, "left": 0, "width": 100, "height": 100},
            "landmark": {"nose": {"x": 50, "y": 40}},
        }
        web = {"pagesWithMatchingImages": [{"url": "https://x.com/a/status/1"}]}
        with TemporaryDirectory() as directory:
            image = Path(directory) / "person.jpeg"
            image.write_bytes(b"photo")
            with (
                patch("facechain.cli.required_env", return_value="configured"),
                patch("facechain.cli.detect_face", return_value=face),
                patch("facechain.cli.reverse_image_search", return_value=web),
                patch("facechain.cli.commit_hash") as commit,
            ):
                run(image, Path(directory) / "artifacts", dry_run=True)
            commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
