Angel Email — Gmail label downloader to .eml and SQLite

This CLI logs into a Gmail account (OAuth2), downloads all emails matching
specified labels, saves each email as a `.eml` file under the project root
`emails/` directory, parses headers/bodies, and appends them as rows in a
SQLite database (`emails/emails.db`).

Features

- OAuth2 login using Google API (read-only scope)
- List available Gmail labels
- Download messages filtered by label names (and optional Gmail search query)
- Save raw `.eml` files organized by label folders (e.g., `./emails/INBOX/`, `./emails/Work/`)
- Extract and save email attachments organized by message
- Parse headers and text/html bodies
- Upsert into SQLite with a simple schema
- Mark downloaded emails in Gmail with a custom label (optional)

Prerequisites

- Python 3.13+
- A Google Cloud project with Gmail API enabled
- OAuth 2.0 Client ID (Desktop) credentials JSON downloaded

Setup

1. Enable Gmail API and create OAuth client credentials (Desktop App):
   - <https://console.cloud.google.com/apis/library/gmail.googleapis.com>
   - Create OAuth Client ID (Application type: Desktop App).
   - Download the JSON file.
2. Place the credentials file at the project root as `credentials.json` (or
pass a custom path via `--credentials`).
3. Install the package or run it with `uv`:
   - Using uv (recommended):
     - `uv sync` (creates/updates a project env)
     - Run the CLI without installing globally: `uv run angel-email --help`
   - Or using pip inside a virtual environment:
     - `python -m venv .venv && source .venv/bin/activate`
     - `pip install -e .`
     - Now the CLI is available as `angel-email`

Command-line usage

- List labels:
  - `angel-email --list-labels`
- Download and parse messages by labels (comma-separated names):
  - `angel-email --labels INBOX,Work`
  - For labels containing spaces, quote the value:
    - `angel-email --labels "My Label,Another Label"`
- Limit number of messages:
  - `angel-email --labels INBOX --max 100`
- Add an extra Gmail query (e.g., last year only):
  - `angel-email --labels INBOX --query "newer_than:1y"`
- Mark downloaded emails with a label in Gmail:
  - `angel-email --labels INBOX --mark-downloaded "Downloaded"`
  - The label will be created automatically if it doesn't exist
  - This helps track which emails have been backed up locally

By default the tool uses:

- Credentials: `./credentials.json`
- Token storage: `./token.json`
- Emails directory: `./emails/`
- Database path: `./emails/emails.db`

You can override with flags:

- `--credentials /path/to/client_secret.json`
- `--token /path/to/token.json`
- `--emails-dir /some/dir`
- `--db /some/dir/emails.db`

Database schema
Table `emails` columns:

- `id` (INTEGER PRIMARY KEY)
- `gmail_id` (TEXT UNIQUE)
- `thread_id` (TEXT)
- `message_id` (TEXT)
- `subject` (TEXT)
- `from_addr`, `to_addrs`, `cc_addrs`, `bcc_addrs` (TEXT)
- `date` (TEXT)
- `snippet` (TEXT)
- `text_body` (TEXT)
- `html_body` (TEXT)
- `headers_json` (TEXT)
- `raw_eml_path` (TEXT)
- `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)

Notes

- The first run will open a browser window to authenticate your Google account
and consent to the Gmail read-only scope.
- If you see label not found errors, run `angel-email --list-labels` to
discover the exact label names.
- Emails are organized in folders by label name (e.g., `emails/INBOX/`, `emails/Work/`)
- Attachments are saved in `emails/{LABEL}/attachments/{gmail_id}/` folders
- `.eml` files are named by Gmail message ID (e.g., `emails/INBOX/1785d3f0fe8a12ab.eml`)
- The tool upserts by `gmail_id` so re-running will refresh rows and skip duplicates.
- Use `--mark-downloaded` to add a Gmail label to downloaded messages, making
it easy to track what's been backed up

How to run (important)

- Preferred: `uv run angel-email --help` (no global install required).
- If you installed with pip (editable or regular): use the console script `angel-email`.
- Running as `python -m angel_email` from a fresh source checkout will not
work unless the package is installed or your PYTHONPATH includes `src/`
(this repo uses a src/ layout). To use `python -m`, first install the
package: `pip install -e .` or run with `uv run angel-email ...`.

Troubleshooting

- Credentials file missing: ensure `credentials.json` is at project root or provide `--credentials`.
- Token/consent issues: delete `token.json` and re-run to re-consent.
- Rate limits: if you have many emails, consider using `--max` and/or `--query` to batch downloads.

Development

- Entry point is defined in `pyproject.toml` as `angel_email:main`.
- Source code lives in `src/angel_email/`.
