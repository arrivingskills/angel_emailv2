from __future__ import annotations

from pathlib import Path
from typing import Optional
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Scopes required for modifying labels and messages (read + modify + labels)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]


def load_credentials(credentials_path: Path, token_path: Path) -> Credentials:
    """
    Load OAuth credentials. If token doesn't exist or is invalid, start local OAuth flow.
    credentials_path: Path to OAuth client secrets JSON downloaded from Google Cloud Console.
    token_path: Path to save/restore the token JSON.
    Returns a valid Credentials object.
    """
    creds: Optional[Credentials] = None

    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            creds = None
    
        # If a token exists, verify it contains the required scopes. If not,
        # remove it so the user is prompted to re-authorize with expanded scopes.
        if token_path.exists():
            try:
                raw = token_path.read_text()
                data = json.loads(raw) if raw else {}
            except Exception:
                data = {}

            token_scopes = data.get("scopes") or data.get("scope") or []
            if isinstance(token_scopes, str):
                # space-separated scopes string
                token_scopes = token_scopes.split()

            token_scopes_set = set(token_scopes or [])
            required_scopes_set = set(SCOPES)

            if not required_scopes_set.issubset(token_scopes_set):
                # Token does not include required scopes; remove it to force re-auth.
                try:
                    token_path.unlink()
                    print(
                        f"Existing token at {token_path} lacks required scopes; removed to force re-auth."
                    )
                except Exception:
                    print(
                        f"Warning: failed to remove token at {token_path}; continuing to re-auth."
                    )
                creds = None
            else:
                try:
                    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
                    print(f"Using existing token at {token_path} with required scopes.")
                except Exception:
                    creds = None

        if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                    print("Warning: failed to refresh token; re-running OAuth flow.")
                    creds = None
        if not creds or not creds.valid:
            # Run local server flow
            print("Starting local OAuth flow to obtain credentials with required scopes:")
            for s in SCOPES:
                print(f"  - {s}")
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())
        try:
            print(f"Saved credentials to {token_path}")
        except Exception:
            pass

    return creds
