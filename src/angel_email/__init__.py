from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from angel_email.gmail_auth import load_credentials
from angel_email.gmail_client import (
    build_gmail_service,
    resolve_label_ids,
    list_labels,
    list_message_ids,
    get_message_raw,
    get_message_metadata,
    save_eml,
    save_attachment,
    clear_attachments_dir,
    create_label_if_not_exists,
    add_label_to_message,
)
from angel_email.email_parser import parse_eml_bytes, extract_attachments, parse_message_object
from angel_email import db as dbmod


def project_root() -> Path:
    """Return the working directory used for default paths.

    The CLI defaults (credentials.json, token.json, emails/, emails/emails.db)
    should be relative to where the command is executed, not the package file
    location. Using CWD aligns with README examples and typical CLI behavior.
    """
    return Path.cwd()


def main(argv: Optional[List[str]] = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = project_root()

    parser = argparse.ArgumentParser(
        prog="angel-emails",
        description="Login to Gmail and download emails by labels, save .eml, and parse into SQLite",
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=root / "credentials.json",
        help="Path to OAuth client credentials JSON (download from Google Cloud Console)",
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=root / "token.json",
        help="Path to OAuth token JSON (will be created/refreshed)",
    )
    parser.add_argument(
        "--labels",
        type=str,
        default="",
        help="Comma-separated Gmail label names to filter (e.g., INBOX,Work). Required unless --list-labels",
    )
    parser.add_argument(
        "--list-labels",
        action="store_true",
        help="List available labels and exit",
    )
    parser.add_argument(
        "--emails-dir",
        type=Path,
        default=root / "emails",
        help="Directory to save downloaded .eml files (default: project_root/emails)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=root / "emails" / "emails.db",
        help="SQLite database path (default: project_root/emails/emails.db)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Max number of emails to fetch (default: no limit)",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Additional Gmail search query (e.g., 'newer_than:1y')",
    )
    parser.add_argument(
        "--mark-downloaded",
        type=str,
        default=None,
        metavar="LABEL",
        help="Gmail label name to apply to downloaded emails (e.g., 'Downloaded'). Label will be created if it doesn't exist.",
    )

    args = parser.parse_args(argv)

    # Authenticate
    if not args.credentials.exists():
        print(f"Credentials file not found: {args.credentials}")
        print(
            "Create OAuth credentials in Google Cloud Console and download as credentials.json"
        )
        sys.exit(2)

    creds = load_credentials(args.credentials, args.token)
    service = build_gmail_service(creds)

    if args.list_labels:
        label_map = list_labels(service)
        for name, lid in sorted(label_map.items()):
            print(f"{name}: {lid}")
        return

    label_names = [s.strip() for s in args.labels.split(",") if s.strip()]
    if not label_names:
        print(
            "--labels is required (comma-separated names), or use --list-labels to view options."
        )
        sys.exit(2)

    try:
        label_ids = resolve_label_ids(service, label_names)
    except ValueError as e:
        print(str(e))
        sys.exit(2)

    # Prepare output directories and DB
    base_emails_dir: Path = args.emails_dir
    base_emails_dir.mkdir(parents=True, exist_ok=True)
    db_path: Path = args.db
    conn = dbmod.connect(db_path)
    dbmod.init_db(conn)

    # Get full label details for mapping
    label_map = list_labels(service)
    label_id_to_name = {v: k for k, v in label_map.items()}

    # Only create/get the "downloaded" label if --mark-downloaded is specified
    downloaded_label_name: str | None = args.mark_downloaded
    downloaded_label_id: str | None = None
    if downloaded_label_name:
        downloaded_label_id = create_label_if_not_exists(service, downloaded_label_name)
        print(f"Will mark downloaded emails with label: {downloaded_label_name}")

    # Fetch message IDs
    print(f"Listing messages for labels: {', '.join(label_names)}")
    # Exclude already-downloaded messages so they are not re-downloaded (only if marking is enabled).
    combined_q = args.query
    if downloaded_label_name:
        # Quote label name to handle spaces properly in Gmail query syntax
        escaped_label = f'"{downloaded_label_name}"' if ' ' in downloaded_label_name else downloaded_label_name
        exclude_q = f"-label:{escaped_label}"
        combined_q = f"{args.query} {exclude_q}" if args.query else exclude_q
    msg_ids = list_message_ids(
        service, label_ids=label_ids, max_results=args.max, q=combined_q
    )
    print(f"Found {len(msg_ids)} messages")

    # Download, save, parse, and upsert
    for idx, mid in enumerate(msg_ids, start=1):
        try:
            raw_bytes = get_message_raw(service, mid)
            meta = get_message_metadata(service, mid)
            thread_id = meta.get("threadId")
            snippet = meta.get("snippet")
            msg_label_ids = meta.get("labelIds", [])

            # Determine primary label folder (use first matching label from user's selection)
            primary_label = label_names[0]  # Default to first requested label
            for label_id in msg_label_ids:
                label_name = label_id_to_name.get(label_id, "")
                if label_name in label_names:
                    primary_label = label_name
                    break

            # Create label-specific directory (strip any extra whitespace)
            label_dir = base_emails_dir / primary_label.strip()
            label_dir.mkdir(parents=True, exist_ok=True)

            # Save .eml file in label folder
            eml_path = save_eml(raw_bytes, label_dir, mid)
            
            # Parse email once and extract all needed data
            parsed, msg = parse_message_object(raw_bytes)
            attachments = extract_attachments(msg)

            # Upsert email data
            dbmod.upsert_email(
                conn,
                gmail_id=mid,
                thread_id=thread_id,
                message_id=parsed.get("message_id"),
                subject=parsed.get("subject"),
                from_addr=parsed.get("from_"),
                to_addrs=parsed.get("to"),
                cc_addrs=parsed.get("cc"),
                bcc_addrs=parsed.get("bcc"),
                date=parsed.get("date"),
                snippet=snippet,
                text_body=parsed.get("text_body"),
                html_body=parsed.get("html_body"),
                headers=parsed.get("headers"),
                raw_eml_path=eml_path,
            )

            # Get the internal email ID for foreign key references
            email_id = dbmod.get_email_id_by_gmail_id(conn, mid)
            if email_id:
                # Save label associations (filter out None values)
                label_tuples = [
                    (label_id_to_name[lid], lid)
                    for lid in msg_label_ids
                    if lid in label_id_to_name
                ]
                if label_tuples:
                    dbmod.insert_email_labels(
                        conn, email_id=email_id, labels=label_tuples
                    )

                # Delete existing attachments before re-inserting (handles upsert case)
                dbmod.delete_attachments_for_email(conn, email_id)
                clear_attachments_dir(label_dir, mid)
                
                # Save attachments to disk and record in DB
                for attachment in attachments:
                    try:
                        attachment_path = save_attachment(
                            attachment["data"], label_dir, mid, attachment["filename"]
                        )
                        dbmod.insert_attachment(
                            conn,
                            email_id=email_id,
                            filename=attachment["filename"],
                            content_type=attachment["content_type"],
                            size=attachment["size"],
                            file_path=attachment_path,
                        )
                    except Exception as e:
                        print(
                            f"  Warning: Failed to save attachment {attachment['filename']}: {e}"
                        )

            # Mark email as downloaded in Gmail if option is enabled
            if downloaded_label_id:
                try:
                    add_label_to_message(service, mid, downloaded_label_id)
                except Exception as e:
                    print(f"  Warning: Failed to add label to message {mid}: {e}")

            if idx % 20 == 0 or idx == len(msg_ids):
                attachments_count = len(attachments) if attachments else 0
                print(
                    f"Processed {idx}/{len(msg_ids)} (label: {primary_label}, attachments: {attachments_count})"
                )
        except KeyboardInterrupt:
            print("Interrupted by user")
            conn.close()
            return
        except Exception as e:
            print(f"Error processing message {mid}: {e}")

    # Export all emails to CSV alongside the database
    csv_path = db_path.parent / "emails.csv"
    dbmod.export_csv(conn, csv_path)
    print(f"Exported emails to {csv_path}")

    conn.close()
    print("Done.")
