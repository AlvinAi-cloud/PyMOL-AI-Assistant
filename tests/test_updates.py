import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from pymol_ai_assistant.updates import (
    MAX_RESPONSE_BYTES, REPOSITORY_URL, UpdateError, fetch_latest,
    installer_name, parse_release,
)


def release(version="0.6.1", system="darwin", machine="arm64"):
    name = installer_name(version, system, machine)
    return {"tag_name": "v" + version, "draft": False, "prerelease": False,
            "assets": [{"name": name, "state": "uploaded",
                        "browser_download_url": REPOSITORY_URL + "/releases/download/v" + version + "/" + name}]}


class UpdateTests(unittest.TestCase):
    def test_installer_matches_platform_and_architecture(self):
        for system, machine, suffix in [("darwin", "arm64", "macOS-arm64.dmg"),
                ("darwin", "x86_64", "macOS-x86_64.dmg"),
                ("win32", "AMD64", "Windows-x64-Setup.exe"),
                ("linux", "x86_64", "Ubuntu-amd64.deb")]:
            info = parse_release(release(system=system, machine=machine), current="0.6.0", system=system, machine=machine)
            self.assertTrue(info.newer)
            self.assertTrue(info.download_url.endswith(suffix))
        self.assertIsNone(installer_name("0.6.1", "win32", "ARM64"))
        self.assertIsNone(installer_name("0.6.1", "linux", "aarch64"))

    def test_numeric_version_order_does_not_downgrade(self):
        self.assertTrue(parse_release(release("0.10.0"), current="0.6.0").newer)
        for current in ["0.6.1", "0.7.0", "1.0.0"]:
            self.assertFalse(parse_release(release(), current=current).newer)

    def test_missing_or_untrusted_asset_uses_release_page(self):
        data = release()
        data["assets"] = []
        self.assertIsNone(parse_release(data).download_url)
        data = release()
        data["assets"][0]["browser_download_url"] = "https://example.com/unrelated.exe"
        info = parse_release(data, system="darwin", machine="arm64")
        self.assertIsNone(info.download_url)
        self.assertEqual(info.release_url, REPOSITORY_URL + "/releases/tag/v0.6.1")

    def test_rejects_draft_prerelease_and_malformed_metadata(self):
        for data in [[], {}, {**release(), "draft": True}, {**release(), "prerelease": True},
                {**release(), "tag_name": "v0.7.0rc1"}, {**release(), "tag_name": "../../bad"},
                {**release(), "assets": {}}, {**release(), "tag_name": 6}]:
            with self.assertRaises(UpdateError):
                parse_release(data)

    def test_fetch_is_anonymous_bounded_and_uses_timeout(self):
        with patch("pymol_ai_assistant.updates.urlopen", return_value=io.BytesIO(json.dumps(release()).encode())) as request:
            self.assertEqual(fetch_latest().version, "0.6.1")
        args, kwargs = request.call_args
        self.assertEqual(kwargs["timeout"], 12)
        self.assertIsNone(args[0].get_header("Authorization"))
        self.assertIsNone(args[0].data)
        for body in [b"not JSON", b"a" * (MAX_RESPONSE_BYTES + 1)]:
            with patch("pymol_ai_assistant.updates.urlopen", return_value=io.BytesIO(body)):
                with self.assertRaises(UpdateError):
                    fetch_latest()

    def test_network_failures_are_actionable(self):
        for error, message in [(URLError("offline"), "internet connection"),
                (TimeoutError(), "internet connection"),
                (HTTPError("test", 403, "rate limited", {}, None), "limiting"),
                (HTTPError("test", 429, "rate limited", {}, None), "limiting"),
                (HTTPError("test", 404, "not found", {}, None), "No public release"),
                (HTTPError("test", 500, "server error", {}, None), "Try again later")]:
            with patch("pymol_ai_assistant.updates.urlopen", side_effect=error):
                with self.assertRaisesRegex(UpdateError, message):
                    fetch_latest()
