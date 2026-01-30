import base64
from unittest.mock import MagicMock

from pathlib import Path

from angel_email.gmail_client import create_label_if_not_exists, add_label_to_message


def test_create_label_and_add_label_to_message():
    service = MagicMock()

    # Mock labels.list to return empty list so create is called
    service.users.return_value.labels.return_value.list.return_value.execute.return_value = {"labels": []}
    # Mock labels.create to return a created label id
    service.users.return_value.labels.return_value.create.return_value.execute.return_value = {"id": "DLID"}

    label_id = create_label_if_not_exists(service, "00downloaded")
    assert label_id == "DLID"
    service.users.return_value.labels.return_value.create.assert_called_once()

    # Now test add_label_to_message calls modify with proper body
    service.users.return_value.messages.return_value.modify.return_value.execute.return_value = {}
    add_label_to_message(service, "msg123", "DLID")

    service.users.return_value.messages.return_value.modify.assert_called_once()
    args, kwargs = service.users.return_value.messages.return_value.modify.call_args
    # Ensure userId and id were passed as kwargs and addLabelIds contains our label
    assert kwargs.get("userId") == "me"
    assert kwargs.get("id") == "msg123"
    assert kwargs.get("body") == {"addLabelIds": ["DLID"]}


if __name__ == "__main__":
    test_create_label_and_add_label_to_message()
    print("OK")
