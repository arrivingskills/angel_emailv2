from __future__ import annotations

import csv
import json
import sqlite3
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA = {
    "emails": (
        """
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gmail_id TEXT UNIQUE,
            thread_id TEXT,
            message_id TEXT,
            subject TEXT,
            from_addr TEXT,
            to_addrs TEXT,
            cc_addrs TEXT,
            bcc_addrs TEXT,
            date TEXT,
            snippet TEXT,
            text_body TEXT,
            html_body TEXT,
            headers_json TEXT,
            raw_eml_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    ),
    "attachments": (
        """
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT,
            size INTEGER,
            file_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_attachments_email_id ON attachments(email_id);
        """
    ),
    "email_labels": (
        """
        CREATE TABLE IF NOT EXISTS email_labels (
            email_id INTEGER NOT NULL,
            label_name TEXT NOT NULL,
            label_id TEXT NOT NULL,
            PRIMARY KEY (email_id, label_name),
            FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_email_labels_label_name ON email_labels(label_name);
        """
    ),
}


def normalize_date(raw_date: Optional[str]) -> Optional[str]:
    """Convert an RFC 2822 date string to yyyy/mm/dd hh:mm format.

    If parsing fails the original value is returned unchanged.
    """
    if not raw_date:
        return raw_date
    try:
        dt = parsedate_to_datetime(raw_date)
        return dt.strftime("%Y/%m/%d %H:%M")
    except Exception:
        return raw_date


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    for _, ddl in SCHEMA.items():
        conn.executescript(ddl)
    conn.commit()


def upsert_email(
    conn: sqlite3.Connection,
    *,
    gmail_id: str,
    thread_id: Optional[str],
    message_id: Optional[str],
    subject: Optional[str],
    from_addr: Optional[str],
    to_addrs: Optional[str],
    cc_addrs: Optional[str],
    bcc_addrs: Optional[str],
    date: Optional[str],
    snippet: Optional[str],
    text_body: Optional[str],
    html_body: Optional[str],
    headers: Optional[Dict[str, Any]],
    raw_eml_path: Path,
) -> None:
    headers_json = json.dumps(headers or {}, ensure_ascii=False)
    date = normalize_date(date)
    conn.execute(
        """
        INSERT INTO emails (
            gmail_id, thread_id, message_id, subject, from_addr, to_addrs, cc_addrs, bcc_addrs,
            date, snippet, text_body, html_body, headers_json, raw_eml_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(gmail_id) DO UPDATE SET
            thread_id=excluded.thread_id,
            message_id=excluded.message_id,
            subject=excluded.subject,
            from_addr=excluded.from_addr,
            to_addrs=excluded.to_addrs,
            cc_addrs=excluded.cc_addrs,
            bcc_addrs=excluded.bcc_addrs,
            date=excluded.date,
            snippet=excluded.snippet,
            text_body=excluded.text_body,
            html_body=excluded.html_body,
            headers_json=excluded.headers_json,
            raw_eml_path=excluded.raw_eml_path
        ;
        """,
        (
            gmail_id,
            thread_id,
            message_id,
            subject,
            from_addr,
            to_addrs,
            cc_addrs,
            bcc_addrs,
            date,
            snippet,
            text_body,
            html_body,
            headers_json,
            str(raw_eml_path),
        ),
    )
    conn.commit()


def get_email_id_by_gmail_id(conn: sqlite3.Connection, gmail_id: str) -> Optional[int]:
    """Get the internal email id from gmail_id."""
    cursor = conn.execute("SELECT id FROM emails WHERE gmail_id = ?", (gmail_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def delete_attachments_for_email(conn: sqlite3.Connection, email_id: int) -> None:
    """Delete all attachments for an email (used before re-inserting on upsert)."""
    conn.execute("DELETE FROM attachments WHERE email_id = ?", (email_id,))
    conn.commit()


def insert_attachment(
    conn: sqlite3.Connection,
    *,
    email_id: int,
    filename: str,
    content_type: str,
    size: int,
    file_path: Path,
) -> None:
    """Insert attachment metadata into the attachments table.

    Does NOT commit — callers should commit once after inserting all attachments
    for a message to keep the batch atomic and reduce round-trips.
    """
    conn.execute(
        """
        INSERT INTO attachments (email_id, filename, content_type, size, file_path)
        VALUES (?, ?, ?, ?, ?)
        """,
        (email_id, filename, content_type, size, str(file_path)),
    )


def insert_email_labels(
    conn: sqlite3.Connection,
    *,
    email_id: int,
    labels: list[tuple[str, str]],
) -> None:
    """Insert label associations for an email. labels is list of (label_name, label_id) tuples."""
    # First, remove existing labels for this email
    conn.execute("DELETE FROM email_labels WHERE email_id = ?", (email_id,))
    # Insert new labels
    for label_name, label_id in labels:
        conn.execute(
            """
            INSERT INTO email_labels (email_id, label_name, label_id)
            VALUES (?, ?, ?)
            """,
            (email_id, label_name, label_id),
        )
    conn.commit()


def export_csv(conn: sqlite3.Connection, csv_path: Path) -> None:
    """Export all emails to a CSV file alongside the database."""
    # Order by created_at (always ISO timestamp) rather than the 'date' column,
    # because normalize_date can fall back to a raw RFC 2822 string that sorts
    # non-chronologically as plain text, silently scrambling the export order.
    cursor = conn.execute(
        """
        SELECT gmail_id, thread_id, message_id, subject, from_addr,
               to_addrs, cc_addrs, bcc_addrs, date, snippet,
               text_body, html_body, raw_eml_path
        FROM emails
        ORDER BY created_at
        """
    )
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
