#!/usr/bin/env python3
"""Validate YouTube OAuth token — refresh if expired, always exit 0 if refresh_token exists."""

from __future__ import annotations
import sys
import pickle
import base64
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    try:
        from google.auth.transport.requests import Request
        from youtube_uploader import _load_credentials_from_token

        creds = _load_credentials_from_token()

        if creds.valid:
            print("OK: YouTube token is valid for upload")
            # Save refreshed pickle locally so this run can upload
            with open("youtube_token.pickle", "wb") as f:
                pickle.dump(creds, f)
            return 0

        # Not valid — try explicit refresh
        if creds.refresh_token:
            print("INFO: Token expired — attempting refresh...")
            try:
                creds.refresh(Request())
                if creds.valid:
                    # Save refreshed token to pickle for this run
                    with open("youtube_token.pickle", "wb") as f:
                        pickle.dump(creds, f)
                    # Also update YOUTUBE_TOKEN_BASE64 env for the current process
                    new_b64 = base64.b64encode(pickle.dumps(creds)).decode()
                    print(f"OK: Token refreshed successfully")
                    # Try to persist back to GitHub secret if PAT available
                    _try_persist_secret(creds)
                    return 0
                else:
                    print("ERROR: Token refresh succeeded but credentials still invalid")
                    return 1
            except Exception as e:
                print(f"ERROR: Token refresh failed: {e}")
                return 1
        else:
            print("ERROR: No refresh_token available — need full re-auth")
            return 1

    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


def _try_persist_secret(creds):
    """Best-effort push of refreshed token back to GitHub secret."""
    import pickle, json, urllib.request
    try:
        from nacl import bindings
        pat = os.environ.get("GH_PAT_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
        repo = os.environ.get("GITHUB_REPOSITORY", "Mohan-Kumar-Swamynathan/history")
        if not pat:
            print("INFO: No PAT — skipping secret update (token saved to pickle for this run)")
            return

        token_b64 = base64.b64encode(pickle.dumps(creds)).decode()
        headers = {
            "Authorization": f"token {pat}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            key_data = json.loads(r.read())

        pub_key_bytes = base64.b64decode(key_data["key"])
        encrypted = bindings.crypto_box_seal(token_b64.encode(), pub_key_bytes)
        encrypted_b64 = base64.b64encode(encrypted).decode()

        payload = json.dumps({"encrypted_value": encrypted_b64, "key_id": key_data["key_id"]}).encode()
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/actions/secrets/YOUTUBE_TOKEN_BASE64",
            data=payload, headers=headers, method="PUT",
        )
        urllib.request.urlopen(req, timeout=10)
        print("✅ Refreshed token persisted back to GitHub secret")
    except Exception as e:
        print(f"INFO: Could not persist to GitHub secret ({e}) — pickle saved for this run only")


if __name__ == "__main__":
    raise SystemExit(main())
