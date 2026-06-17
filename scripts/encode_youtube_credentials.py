#!/usr/bin/env python3
"""Generate CLIENT_SECRETS_BASE64 and YOUTUBE_TOKEN_BASE64 for GitHub Secrets."""

import argparse
import base64
import pickle
import sys
from pathlib import Path


def encode_client_secrets(client_secrets_path: Path) -> str:
    return base64.b64encode(client_secrets_path.read_bytes()).decode("ascii")


def run_oauth_flow(client_secrets_path: Path) -> str:
    from google_auth_oauthlib.flow import InstalledAppFlow
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), scopes)
    credentials = flow.run_local_server(port=0)
    return base64.b64encode(pickle.dumps(credentials)).decode("ascii")


def main():
    parser = argparse.ArgumentParser(description="Encode YouTube OAuth credentials")
    parser.add_argument("--client-secrets", required=True)
    parser.add_argument("--skip-oauth", action="store_true")
    args = parser.parse_args()

    client_path = Path(args.client_secrets)
    if not client_path.exists():
        print(f"Error: file not found: {client_path}", file=sys.stderr)
        sys.exit(1)

    print("\n=== Add these to GitHub Secrets ===\n")
    print(f"CLIENT_SECRETS_BASE64:\n{encode_client_secrets(client_path)}\n")

    if not args.skip_oauth:
        print("Opening browser for YouTube OAuth...")
        print(f"YOUTUBE_TOKEN_BASE64:\n{run_oauth_flow(client_path)}\n")
    else:
        print("(Run without --skip-oauth to generate YOUTUBE_TOKEN_BASE64)")


if __name__ == "__main__":
    main()
