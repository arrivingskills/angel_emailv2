from __future__ import annotations

import email
from email import policy
from email.message import Message
from typing import Any, Dict, List, Optional, Tuple


def parse_eml_bytes(raw_bytes: bytes) -> Dict[str, Any]:
    """
    Parse raw RFC822 bytes into a dict with common fields.
    Returns keys: message_id, subject, from_, to, cc, bcc, date, text_body, html_body, headers
    """
    parsed, _ = parse_message_object(raw_bytes)
    return parsed


def parse_message_object(raw_bytes: bytes) -> Tuple[Dict[str, Any], Message]:
    """
    Parse raw RFC822 bytes into a dict with common fields and return the Message object.
    Returns tuple of (parsed_dict, Message) to allow reuse of the Message for attachment extraction.
    """
    msg: Message = email.message_from_bytes(raw_bytes, policy=policy.default)

    def get_header(name: str) -> Optional[str]:
        val = msg.get(name)
        if val is None:
            return None
        # The emails library under policy.default returns str for headers
        return str(val)

    text_body, html_body = extract_bodies(msg)

    headers = {k: str(v) for (k, v) in msg.items()}

    parsed = {
        "message_id": get_header("Message-ID"),
        "subject": get_header("Subject"),
        "from_": get_header("From"),
        "to": get_header("To"),
        "cc": get_header("Cc"),
        "bcc": get_header("Bcc"),
        "date": get_header("Date"),
        "text_body": text_body,
        "html_body": html_body,
        "headers": headers,
    }
    return parsed, msg


def _decode_part(part: Message) -> Optional[str]:
    """Try every available method to extract decoded text from a MIME part."""
    # Method 1: policy.default EmailMessage API
    try:
        content = part.get_content()
        if content is not None:
            return str(content)
    except Exception:
        pass

    # Method 2: compat32 decoded payload
    try:
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes):
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        if isinstance(payload, str):
            return payload
    except Exception:
        pass

    # Method 3: raw unencoded payload (last resort)
    try:
        payload = part.get_payload(decode=False)
        if isinstance(payload, str):
            return payload
    except Exception:
        pass

    return None


def extract_bodies(msg: Message) -> Tuple[Optional[str], Optional[str]]:
    """Extract the best-effort text and HTML payloads from the message."""
    text_body: Optional[str] = None
    html_body: Optional[str] = None

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            ctype = part.get_content_type()
            if ctype not in ("text/plain", "text/html"):
                continue
            if ctype == "text/plain" and text_body is not None:
                continue
            if ctype == "text/html" and html_body is not None:
                continue
            payload = _decode_part(part)
            if payload is None:
                print(
                    f"  Warning: could not extract content from {ctype} part; body may be incomplete"
                )
            elif ctype == "text/plain":
                text_body = payload
            else:
                html_body = payload
    else:
        ctype = msg.get_content_type()
        payload = _decode_part(msg)
        if payload is None and ctype in ("text/plain", "text/html"):
            print(
                f"  Warning: could not extract content from {ctype} message; body may be incomplete"
            )
        if ctype == "text/plain":
            text_body = payload
        elif ctype == "text/html":
            html_body = payload

    return text_body, html_body


def extract_attachments(msg: Message) -> List[Dict[str, Any]]:
    """
    Extract attachments from an email message.

    Returns list of dicts with keys:
    - filename: str (name of the attachment)
    - content_type: str (MIME type)
    - data: bytes (binary content)
    - size: int (size in bytes)
    """
    attachments: List[Dict[str, Any]] = []

    # Outlook/Exchange internal metadata filenames that should never be
    # treated as real attachments.  These MIME parts carry custom form
    # properties, voting buttons, read-receipt flags, etc.
    _OUTLOOK_JUNK_PREFIXES = (
        "EML*OECUSTOMPROPERTY",
        "EML*OECUSTOMHTML",
        "EML*OE",
    )

    # TNEF and other proprietary Outlook MIME types
    _OUTLOOK_JUNK_CONTENT_TYPES = {
        "application/ms-tnef",
        "application/x-ms-tnef",
        "application/vnd.ms-tnef",
    }

    # Known Outlook/Exchange junk filenames (exact, case-insensitive)
    _OUTLOOK_JUNK_FILENAMES = {
        "WINMAIL.DAT",
        "WIN.DAT",
    }

    def _is_outlook_junk(filename: str, content_type: str) -> bool:
        upper = filename.upper() if filename else ""
        if any(upper.startswith(pfx) for pfx in _OUTLOOK_JUNK_PREFIXES):
            return True
        if upper in _OUTLOOK_JUNK_FILENAMES:
            return True
        if content_type.lower() in _OUTLOOK_JUNK_CONTENT_TYPES:
            return True
        return False

    if msg.is_multipart():
        for part in msg.walk():
            # Skip multipart containers
            if part.get_content_maintype() == "multipart":
                continue

            # Check if this part is an attachment
            content_disposition = part.get("Content-Disposition", "")
            filename = part.get_filename()

            # Skip Outlook/Exchange proprietary extension data
            if _is_outlook_junk(filename or "", part.get_content_type()):
                continue

            # Parts with Content-Disposition: attachment or inline with filename
            # or parts with filename in Content-Type are considered attachments
            is_attachment = (
                "attachment" in content_disposition.lower()
                or ("inline" in content_disposition.lower() and filename)
                or filename is not None
            )

            # Also skip text/plain and text/html that are the main body
            if not is_attachment:
                content_type = part.get_content_type()
                if content_type in ("text/plain", "text/html"):
                    continue

            if is_attachment and filename:
                try:
                    # Get the attachment data
                    data = part.get_payload(decode=True)
                    if data:
                        attachments.append(
                            {
                                "filename": filename,
                                "content_type": part.get_content_type(),
                                "data": data,
                                "size": len(data),
                            }
                        )
                except Exception as e:
                    print(
                        f"  Warning: could not decode attachment '{filename}': {e}"
                    )
                    continue
    else:
        # Non-multipart message: check if the message itself is an attachment
        # (uncommon but valid per RFC 2183, e.g. a forwarded .eml).
        content_disposition = msg.get("Content-Disposition", "")
        filename = msg.get_filename()

        if _is_outlook_junk(filename or "", msg.get_content_type()):
            return attachments

        is_attachment = "attachment" in content_disposition.lower() or (
            "inline" in content_disposition.lower() and filename
        )

        if is_attachment and filename:
            try:
                data = msg.get_payload(decode=True)
                if data:
                    attachments.append(
                        {
                            "filename": filename,
                            "content_type": msg.get_content_type(),
                            "data": data,
                            "size": len(data),
                        }
                    )
            except Exception:
                pass

    return attachments
