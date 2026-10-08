#!/usr/bin/env python3
"""Fill repository URLs in the Home Assistant integration manifest.

Usage: python3 tools/configure_github.py GITHUB_OWNER [REPO_NAME]
This script does not contact GitHub, push code, or modify credentials.
"""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "custom_components/onvif_camera_control/manifest.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner", help="Your GitHub username or organization name")
    parser.add_argument("repository", nargs="?", default="onvif-camera-control")
    args = parser.parse_args()
    valid = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")
    for label, value in (("owner", args.owner), ("repository", args.repository)):
        if not valid.fullmatch(value):
            parser.error(f"Invalid {label}: {value!r}")
    url = f"https://github.com/{args.owner}/{args.repository}"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["documentation"] = url + "#readme"
    manifest["issue_tracker"] = url + "/issues"
    # The repository owner must exist and have access to this repository.
    manifest["codeowners"] = ["@" + args.owner]
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Configured GitHub metadata for {url}")
    print("Next: publish this source tree on GitHub and check all GitHub Actions.")


if __name__ == "__main__":
    main()
