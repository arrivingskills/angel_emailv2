from __future__ import annotations

import base64
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from googleapiclient.discovery import build, Resource


def build_gmail_service(credentials) -> Resource:
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def list_labels(service: Resource) -> Dict[str, str]:
    """Return mapping of label name -> label id for the authenticated user."""
    resp = service.users().labels().list(userId="me").execute()
    labels = resp.get("labels", [])
    return {lbl["name"]: lbl["id"] for lbl in labels}


def resolve_label_ids(
    service: Resource,
    label_names: Iterable[str],
    label_map: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Resolve label names to IDs.

    Args:
        service: Gmail API service.
        label_names: Names to resolve.
        label_map: Pre-fetched name->id mapping.  When provided the function
            skips the API call, allowing callers to reuse a map they already
            hold and avoid a redundant network round-trip.
    """
    if label_map is None:
        label_map = list_labels(service)
    ids: List[str] = []
    missing: List[str] = []
    for name in label_names:
        name = name.strip()
        if not name:
            continue
        if name in label_map:
            ids.append(label_map[name])
        else:
            missing.append(name)
    if missing:
        raise ValueError(f"Labels not found: {', '.join(missing)}")
    return ids


def list_message_ids(
    service: Resource,
    label_ids: Optional[List[str]] = None,
    max_results: Optional[int] = None,
    q: Optional[str] = None,
) -> List[str]:
    """List message IDs matching given labels and optional Gmail query."""
    user = "me"
    ids: List[str] = []
    page_token: Optional[str] = None
    fetched = 0
    while True:
        params = {"userId": user}
        if label_ids:
            params["labelIds"] = label_ids
        if q:
            params["q"] = q
        if page_token:
            params["pageToken"] = page_token
        if max_results:
            remaining = max_results - fetched
            if remaining <= 0:
                break
            params["maxResults"] = min(500, remaining)
        resp = service.users().messages().list(**params).execute()
        msgs = resp.get("messages", [])
        for m in msgs:
            ids.append(m["id"])
            fetched += 1
            if max_results and fetched >= max_results:
                break
        if max_results and fetched >= max_results:
            break
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids


def get_message_raw(service: Resource, msg_id: str) -> bytes:
    """Fetch the raw RFC822 message as bytes (.eml)."""
    resp = (
        service.users().messages().get(userId="me", id=msg_id, format="raw").execute()
    )
    raw_b64 = resp.get("raw", "")
    # Gmail returns base64url encoded string
    raw_bytes = base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
    return raw_bytes


def get_message_metadata(service: Resource, msg_id: str) -> dict:
    resp = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=msg_id,
            format="metadata",
            metadataHeaders=[
                "Message-ID",
                "Subject",
                "From",
                "To",
                "Cc",
                "Bcc",
                "Date",
            ],
        )
        .execute()
    )
    return resp


import shutil


def save_eml(raw_bytes: bytes, out_dir: Path, gmail_id: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{gmail_id}.eml"
    path.write_bytes(raw_bytes)
    return path


def clear_attachments_dir(out_dir: Path, gmail_id: str) -> None:
    """
    Remove the attachments directory for a message if it exists.
    Called before re-saving attachments to avoid orphaned files on re-runs.
    """
    attachments_dir = out_dir / "attachments" / gmail_id
    if attachments_dir.exists():
        shutil.rmtree(attachments_dir)


def save_attachment(
    attachment_data: bytes, out_dir: Path, gmail_id: str, filename: str
) -> Path:
    """
    Save an attachment to disk in a structured folder.

    Args:
        attachment_data: Binary content of the attachment
        out_dir: Base directory for attachments (e.g., emails/INBOX/attachments)
        gmail_id: Gmail message ID (used for organizing)
        filename: Original filename of the attachment

    Returns:
        Path to the saved attachment file
    """
    # Create attachments subfolder under the label folder
    attachments_dir = out_dir / "attachments" / gmail_id
    attachments_dir.mkdir(parents=True, exist_ok=True)

    # Save the attachment with its original filename
    attachment_path = attachments_dir / filename

    # Handle duplicate filenames by adding a suffix
    counter = 1
    original_stem = attachment_path.stem
    original_suffix = attachment_path.suffix
    while attachment_path.exists():
        attachment_path = (
            attachments_dir / f"{original_stem}_{counter}{original_suffix}"
        )
        counter += 1

    attachment_path.write_bytes(attachment_data)
    return attachment_path


def create_label_if_not_exists(service: Resource, label_name: str) -> str:
    """
    Create a Gmail label if it doesn't exist.

    Args:
        service: Gmail API service instance
        label_name: Name of the label to create

    Returns:
        Label ID (either existing or newly created)
    """
    # Check if label already exists
    label_map = list_labels(service)
    if label_name in label_map:
        return label_map[label_name]

    # Create the label
    label_object = {
        "name": label_name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }

    result = service.users().labels().create(userId="me", body=label_object).execute()
    return result["id"]


def add_label_to_message(service: Resource, msg_id: str, label_id: str) -> None:
    """
    Add a label to a Gmail message.

    Args:
        service: Gmail API service instance
        msg_id: Gmail message ID
        label_id: Label ID to add to the message
    """
    service.users().messages().modify(
        userId="me", id=msg_id, body={"addLabelIds": [label_id]}
    ).execute()
