import sys
sys.path.insert(0, "src")

import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import angel_email


def run_one_scenario(mark_downloaded_arg: str | None):
    tmp = Path(tempfile.mkdtemp())
    try:
        creds = tmp / "credentials.json"
        creds.write_text("{}")
        token = tmp / "token.json"
        emails_dir = tmp / "emails"

        args = [
            "--labels",
            "INBOX",
            "--credentials",
            str(creds),
            "--token",
            str(token),
            "--emails-dir",
            str(emails_dir),
        ]
        if mark_downloaded_arg is not None:
            args += ["--mark-downloaded", mark_downloaded_arg]

        recorded = {}

        def fake_load_credentials(c, t):
            recorded['load_credentials_called'] = True
            return MagicMock()

        def fake_build_service(creds):
            return MagicMock()

        def fake_create_label(service, name):
            recorded['created_label'] = name
            return "DLID"

        def fake_list_message_ids(service, label_ids=None, max_results=None, q=None):
            recorded['q'] = q
            return ["mid1"]

        def fake_get_message_raw(service, mid):
            recorded.setdefault('raws', []).append(mid)
            return b"raw-eml-bytes"

        def fake_get_message_metadata(service, mid):
            return {"threadId": "t1", "snippet": "s1", "labelIds": ["someLabelId"]}

        def fake_save_eml(raw_bytes, out_dir, gmail_id):
            recorded.setdefault('saved', []).append((out_dir, gmail_id))
            out = Path(out_dir) / f"{gmail_id}.eml"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(raw_bytes)
            return out

        def fake_parse_message_object(raw):
            return {}, MagicMock()

        def fake_extract_attachments(msg):
            return []

        # DB stubs
        recorded_db = {}
        def fake_connect(p):
            return MagicMock()

        def fake_init_db(conn):
            recorded_db['init_db'] = True

        def fake_upsert_email(*args, **kwargs):
            recorded_db.setdefault('upsert', []).append(True)

        def fake_get_email_id_by_gmail_id(conn, gid):
            return 1

        def fake_insert_email_labels(conn, email_id, labels):
            recorded_db.setdefault('labels', []).append(labels)

        def fake_delete_attachments_for_email(conn, email_id):
            recorded_db.setdefault('deleted_attachments', []).append(email_id)

        def fake_insert_attachment(*args, **kwargs):
            recorded_db.setdefault('attachments', []).append(True)

        added = []
        def fake_add_label_to_message(service, msg_id, label_id):
            added.append((msg_id, label_id))

        # Patch
        angel_email.load_credentials = fake_load_credentials
        angel_email.build_gmail_service = fake_build_service
        angel_email.create_label_if_not_exists = fake_create_label
        angel_email.resolve_label_ids = lambda service, names, label_map=None: ["INBOXID"]
        angel_email.list_labels = lambda service: {"INBOX": "INBOXID"}
        angel_email.list_message_ids = fake_list_message_ids
        angel_email.get_message_raw = fake_get_message_raw
        angel_email.get_message_metadata = fake_get_message_metadata
        angel_email.save_eml = fake_save_eml
        angel_email.parse_message_object = fake_parse_message_object
        angel_email.extract_attachments = fake_extract_attachments
        angel_email.db.connect = fake_connect
        angel_email.db.init_db = fake_init_db
        angel_email.db.upsert_email = fake_upsert_email
        angel_email.db.get_email_id_by_gmail_id = fake_get_email_id_by_gmail_id
        angel_email.db.insert_email_labels = fake_insert_email_labels
        angel_email.db.delete_attachments_for_email = fake_delete_attachments_for_email
        angel_email.db.insert_attachment = fake_insert_attachment
        angel_email.add_label_to_message = fake_add_label_to_message

        # Run
        angel_email.main(args)

        return recorded, added

    finally:
        shutil.rmtree(tmp)


def test_default_download_label_exclusion():
    """Test that without --mark-downloaded, no exclusion query is added and no label is applied."""
    recorded, added = run_one_scenario(None)
    # Without --mark-downloaded, there should be no label exclusion query
    assert recorded['q'] is None
    # No label should be added to messages
    assert added == []


def test_custom_download_label_name():
    recorded, added = run_one_scenario("MyDownloadedLabel")
    assert recorded['q'] is not None
    assert "-label:MyDownloadedLabel" in recorded['q']
    assert added == [("mid1", "DLID")]


def test_label_with_spaces():
    """Test that label names with spaces are properly quoted in the query."""
    recorded, added = run_one_scenario("My Downloaded Label")
    assert recorded['q'] is not None
    # Label with spaces should be quoted
    assert '-label:"My Downloaded Label"' in recorded['q']
    assert added == [("mid1", "DLID")]


if __name__ == "__main__":
    test_default_download_label_exclusion()
    print("default test OK")
    test_custom_download_label_name()
    print("custom test OK")
    test_label_with_spaces()
    print("label with spaces test OK")
