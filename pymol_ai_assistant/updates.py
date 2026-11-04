"""Read public stable releases; downloads remain a user-initiated browser action."""
from dataclasses import dataclass
import json
import platform
import re
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import __version__

REPOSITORY_URL = "https://github.com/AlvinAi-cloud/PyMOL-AI-Assistant"
RELEASES_URL = REPOSITORY_URL + "/releases/latest"
API_URL = "https://api.github.com/repos/AlvinAi-cloud/PyMOL-AI-Assistant/releases/latest"
MAX_RESPONSE_BYTES = 1_000_000


class UpdateError(Exception):
    """A release could not be checked; the installed app is still usable."""


def version_parts(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise UpdateError("GitHub returned an unsupported release version. Please view the releases page.")
    return tuple(int(part) for part in value.lstrip("v").split("."))


def installer_name(version, system=None, machine=None):
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    suffix = None
    if system == "darwin":
        suffix = {"arm64": "macOS-arm64.dmg", "aarch64": "macOS-arm64.dmg",
                  "x86_64": "macOS-x86_64.dmg", "amd64": "macOS-x86_64.dmg"}.get(machine)
    elif system == "win32" and machine in {"amd64", "x86_64"}:
        suffix = "Windows-x64-Setup.exe"
    elif system.startswith("linux") and machine in {"amd64", "x86_64"}:
        suffix = "Ubuntu-amd64.deb"
    return "PyMOL-AI-Assistant-" + version + "-" + suffix if suffix else None


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    newer: bool
    release_url: str
    download_url: str | None
    installer: str | None


def parse_release(payload, current=__version__, system=None, machine=None):
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        raise UpdateError("GitHub did not return a public stable release. Please view the releases page.")
    tag = payload.get("tag_name")
    parts = version_parts(tag)
    version = tag.lstrip("v")
    name = installer_name(version, system, machine)
    # Construct trusted project URLs instead of displaying arbitrary API links.
    release_url = REPOSITORY_URL + "/releases/tag/" + tag
    expected_url = REPOSITORY_URL + "/releases/download/" + tag + "/" + (name or "")
    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        raise UpdateError("GitHub returned an invalid installer list. Please view the releases page.")
    available = name and any(isinstance(asset, dict) and asset.get("name") == name
                             and asset.get("browser_download_url") == expected_url
                             and asset.get("state") == "uploaded" for asset in assets)
    return ReleaseInfo(version, parts > version_parts(current), release_url,
                       expected_url if available else None, name if available else None)


def fetch_latest(endpoint=API_URL):
    """One anonymous, bounded HTTPS request. No account or molecular data is sent."""
    import certifi
    request = Request(endpoint, headers={"Accept": "application/vnd.github+json",
                      "User-Agent": "PyMOL-AI-Assistant/" + __version__,
                      "X-GitHub-Api-Version": "2022-11-28"})
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with urlopen(request, timeout=12, context=context) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise UpdateError("The release response was too large. Please view the releases page.")
        return parse_release(json.loads(body))
    except HTTPError as error:
        if error.code in {403, 429}:
            raise UpdateError("GitHub is limiting update checks. Try again later or view the releases page.") from error
        if error.code == 404:
            raise UpdateError("No public release was found. Please view the releases page.") from error
        raise UpdateError("GitHub could not complete the update check. Try again later or view the releases page.") from error
    except (URLError, TimeoutError, OSError) as error:
        raise UpdateError("Could not reach GitHub. Check your internet connection and try again, or view the releases page.") from error
    except (ValueError, UnicodeError) as error:
        raise UpdateError("GitHub returned an unreadable release response. Please view the releases page.") from error
