#!/usr/bin/env python3
"""Fail fast in CI when YouTube OAuth token cannot be used for upload."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from youtube_uploader import _load_credentials_from_token

        credentials = _load_credentials_from_token()
        if not credentials.valid:
            print("ERROR: YouTube credentials are not valid after load/refresh")
            return 1
        print("OK: YouTube token is valid for upload")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        print(
            "\nFix: run locally from the history repo:\n"
            "  python3 scripts/encode_youtube_credentials.py --client-secrets client_secrets.json\n"
            "Then update GitHub secret YOUTUBE_TOKEN_BASE64 (and CLIENT_SECRETS_BASE64 if needed)."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
