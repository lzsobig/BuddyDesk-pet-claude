"""
Auto-update checker — checks GitHub Releases for new versions.

Compares config.APP_VERSION with the latest tag on GitHub.
Does NOT auto-download; only notifies via the dynamic island.
"""
import json
import urllib.request
import urllib.error
from typing import Optional

import config

_GITHUB_REPO = "your-org/BuddyDesk"  # Update when repo is published


def check_for_update(current_version: Optional[str] = None) -> Optional[dict]:
    """Check GitHub for a newer release.

    Returns:
        dict with keys (tag, name, url, body) if update available, else None.
    """
    current = current_version or config.APP_VERSION
    url = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None

    tag = data.get("tag_name", "").lstrip("v")
    if not tag:
        return None

    if _version_gt(tag, current):
        return {
            "tag": tag,
            "name": data.get("name", tag),
            "url": data.get("html_url", ""),
            "body": data.get("body", ""),
        }
    return None


def _version_gt(a: str, b: str) -> bool:
    """Simple semver-ish comparison: a > b."""
    def parts(v: str) -> list[int]:
        return [int(x) for x in v.split(".") if x.isdigit()]
    pa, pb = parts(a), parts(b)
    for x, y in zip(pa, pb):
        if x != y:
            return x > y
    return len(pa) > len(pb)
