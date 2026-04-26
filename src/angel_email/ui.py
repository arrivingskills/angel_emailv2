from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import shutil

import flet as ft

import angel_email
from angel_email.gmail_auth import load_credentials
from angel_email.gmail_client import (
    build_gmail_service,
    list_labels as _list_labels,
)


_NAVY = "#0D1B3E"

_LOG_STYLE = ft.TextStyle(size=14, color=_NAVY, font_family="Century Gothic")

_FIELD_STYLE = ft.TextStyle(size=16, color=_NAVY, font_family="Century Gothic")
_LABEL_STYLE = ft.TextStyle(
    size=18,
    color=_NAVY,
    font_family="Century Gothic Bold",
    weight=ft.FontWeight.W_600,
)


def _log(page: ft.Page, log_col: ft.Column, text: str) -> None:
    """Append a line to the log panel and refresh the page."""
    log_col.controls.append(ft.Text(text, selectable=True, style=_LOG_STYLE))
    page.update()


class _PageWriter(io.TextIOBase):
    """Redirect print() output to the Flet log panel."""

    def __init__(self, page: ft.Page, log_col: ft.Column) -> None:
        self._page = page
        self._log_col = log_col

    def write(self, s: str) -> int:
        text = s.rstrip("\n")
        if text:
            _log(self._page, self._log_col, text)
        return len(s)

    def flush(self) -> None:  # noqa: D102
        pass


def _field(label: str, value: str = "", **kw) -> ft.TextField:
    """Create a consistently-styled text field."""
    bgcolor = kw.pop("bgcolor", ft.Colors.WHITE)
    text_style = kw.pop("text_style", _FIELD_STYLE)
    return ft.TextField(
        label=label,
        value=value,
        text_style=text_style,
        label_style=_LABEL_STYLE,
        content_padding=ft.padding.only(left=14, right=14, top=44, bottom=14),
        border_radius=10,
        border_color=ft.Colors.GREY_700,
        focused_border_color=ft.Colors.INDIGO,
        cursor_color=ft.Colors.INDIGO,
        bgcolor=bgcolor,
        **kw,
    )


def main_page(page: ft.Page) -> None:
    page.title = "Angel Email"
    page.window.width = 1104
    page.window.height = 980
    page.padding = 0
    page.bgcolor = ft.Colors.WHITE

    # ── theme ────────────────────────────────────────────────────
    page.theme = ft.Theme(
        color_scheme_seed=ft.Colors.INDIGO,
        font_family="Century Gothic Bold",
    )

    # ── form fields ──────────────────────────────────────────────
    creds = _field(
        "Credentials JSON", str(Path.cwd() / "credentials.json"), expand=True
    )
    token = _field("Token JSON", str(Path.cwd() / "token.json"), expand=True)
    labels = _field(
        "Labels (comma-separated)",
        "INBOX",
        expand=True,
        bgcolor="#F69294",
        text_style=ft.TextStyle(
            size=16,
            color=_NAVY,
            font_family="Century Gothic Bold",
            weight=ft.FontWeight.W_700,
        ),
    )
    emails_dir = _field("Emails dir", str(Path.cwd() / "emails"), expand=True)
    db_path = _field(
        "DB path", str(Path.cwd() / "emails" / "emails.db"), expand=True
    )
    query = _field(
        "Gmail query (optional)",
        expand=True,
        hint_text="e.g. from:boss@company.com after:2024/01/01 has:attachment",
        hint_style=ft.TextStyle(italic=True, color=ft.Colors.GREY_500),
    )
    max_count = _field("Max results", width=150)
    mark_label = _field(
        "Mark-downloaded label",
        expand=True,
        hint_text="e.g. AngelDownloaded",
        hint_style=ft.TextStyle(italic=True, color=ft.Colors.GREY_500),
    )
    backup_dir = _field(
        "Backup folder (drive/path)",
        "/mnt/c/Users/angel/Documents/linux_email_backups",
        expand=True,
    )
    #         str(Path.cwd() / "backups"),
    # Hint for Windows Explorer searches on downloaded .eml files
    explorer_hint = ft.Text(
        "Windows File Explorer tip: after syncing emails, open the 'Emails dir' in Explorer "
        "and you can search using email properties, for example: "
        "subject:invoice from:alice@example.com hasattachment:yes",
        size=15,
        color="#0D1B3E",
        selectable=True,
    )

    # ── log area ─────────────────────────────────────────────────
    log_col = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        auto_scroll=True,
        expand=True,
        tight=True,
        spacing=2,
    )

    log_container = ft.Container(
        content=log_col,
        expand=True,
        bgcolor=ft.Colors.WHITE,
        border=ft.border.all(1, ft.Colors.GREY_600),
        border_radius=10,
        padding=12,
    )

    # ── callbacks ────────────────────────────────────────────────
    def on_list_labels(e: ft.ControlEvent) -> None:
        def _work() -> None:
            try:
                _log(page, log_col, "Listing labels…")
                credentials = load_credentials(
                    Path(creds.value), Path(token.value)
                )
                service = build_gmail_service(credentials)
                lbls = _list_labels(service)
                for name in sorted(lbls.keys()):
                    _log(page, log_col, f"  {name}: {lbls[name]}")
                _log(page, log_col, f"Total: {len(lbls)} labels")
            except Exception as ex:
                _log(page, log_col, f"Error: {ex}")

        page.run_thread(_work)

    def on_start(e: ft.ControlEvent) -> None:
        argv: list[str] = []
        if labels.value:
            argv += ["--labels", labels.value]
        if creds.value:
            argv += ["--credentials", creds.value]
        if token.value:
            argv += ["--token", token.value]
        if emails_dir.value:
            argv += ["--emails-dir", emails_dir.value]
        if db_path.value:
            argv += ["--db", db_path.value]
        if query.value:
            argv += ["--query", query.value]
        if max_count.value:
            argv += ["--max", max_count.value]
        if mark_label.value:
            argv += ["--mark-downloaded", mark_label.value]

        def _work() -> None:
            _log(page, log_col, f"Starting download…  ({' '.join(argv)})")
            old_stdout = sys.stdout
            sys.stdout = _PageWriter(page, log_col)
            try:
                angel_email.main(argv)
            except SystemExit:
                pass
            except Exception as exc:
                _log(page, log_col, f"Error: {exc}")
            finally:
                sys.stdout = old_stdout
            _log(page, log_col, "Done.")

        page.run_thread(_work)

    def on_clear_log(e: ft.ControlEvent) -> None:
        log_col.controls.clear()
        page.update()

    def on_save_log(e: ft.ControlEvent) -> None:
        log_path = Path(emails_dir.value or ".") / "angel_email.log"
        try:
            lines = [
                getattr(ctrl, "value", str(ctrl)) for ctrl in log_col.controls
            ]
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("\n".join(lines), encoding="utf-8")
            _log(page, log_col, f"Log saved to {log_path}")
        except Exception as ex:
            _log(page, log_col, f"Failed to save log: {ex}")

    def on_backup(e: ft.ControlEvent) -> None:
        def _work() -> None:
            try:
                dest_root = Path(backup_dir.value).expanduser()
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                backup_root = dest_root / f"angel_email_backup_{timestamp}"
                backup_root.mkdir(parents=True, exist_ok=True)
                _log(page, log_col, f"Starting backup to {backup_root}…")

                def copy_if_exists(path: Path) -> None:
                    if not path.exists():
                        _log(page, log_col, f"  Skipping missing path: {path}")
                        return
                    if path.is_dir():
                        dest = backup_root / path.name
                        shutil.copytree(path, dest, dirs_exist_ok=True)
                        _log(
                            page,
                            log_col,
                            f"  Copied directory {path} → {dest}",
                        )
                    elif path.is_file():
                        dest = backup_root / path.name
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, dest)
                        _log(page, log_col, f"  Copied file {path} → {dest}")

                # Backup main data directory (includes DB and CSV exports)
                copy_if_exists(Path(emails_dir.value))

                # Backup auth files if present
                if creds.value:
                    copy_if_exists(Path(creds.value))
                if token.value:
                    copy_if_exists(Path(token.value))

                _log(page, log_col, "Backup complete.")
            except Exception as ex:
                _log(page, log_col, f"Backup error: {ex}")

        page.run_thread(_work)

    # ── action buttons ───────────────────────────────────────────
    btn_list = ft.ElevatedButton(
        "List Labels",
        icon=ft.Icons.LABEL_OUTLINE,
        on_click=on_list_labels,
        style=ft.ButtonStyle(
            padding=ft.padding.symmetric(horizontal=24, vertical=14)
        ),
    )
    btn_start = ft.FilledButton(
        "Start Download",
        icon=ft.Icons.DOWNLOAD,
        on_click=on_start,
        style=ft.ButtonStyle(
            padding=ft.padding.symmetric(horizontal=24, vertical=14)
        ),
    )
    btn_clear = ft.OutlinedButton(
        "Clear Log",
        icon=ft.Icons.DELETE_OUTLINE,
        on_click=on_clear_log,
        style=ft.ButtonStyle(
            padding=ft.padding.symmetric(horizontal=20, vertical=14)
        ),
    )
    btn_save_log = ft.OutlinedButton(
        "Save Log",
        icon=ft.Icons.SAVE_ALT,
        on_click=on_save_log,
        style=ft.ButtonStyle(
            padding=ft.padding.symmetric(horizontal=20, vertical=14)
        ),
    )
    btn_backup = ft.OutlinedButton(
        "Backup Data",
        icon=ft.Icons.CLOUD_UPLOAD,
        on_click=on_backup,
        style=ft.ButtonStyle(
            padding=ft.padding.symmetric(horizontal=20, vertical=14)
        ),
    )

    # ── layout ───────────────────────────────────────────────────
    header = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.EMAIL, size=28, color=ft.Colors.INDIGO),
                ft.Text(
                    "Angel Email",
                    theme_style=ft.TextThemeStyle.HEADLINE_SMALL,
                    color="#0D1B3E",
                    weight=ft.FontWeight.W_600,
                    font_family="Century Gothic Bold",
                ),
            ],
            spacing=10,
        ),
        margin=ft.margin.only(bottom=4),
    )

    form = ft.Container(
        content=ft.Column(
            [
                header,
                creds,
                token,
                labels,
                ft.Row([emails_dir, db_path], spacing=12),
                explorer_hint,
                ft.Row([query, max_count, mark_label], spacing=12),
                backup_dir,
                ft.Row(
                    [btn_list, btn_start, btn_backup, btn_clear, btn_save_log],
                    spacing=12,
                ),
            ],
            spacing=14,
            tight=True,
        ),
        bgcolor=ft.Colors.GREY_50,
        border_radius=14,
        border=ft.border.all(1, ft.Colors.GREY_400),
        padding=24,
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=8,
            color=ft.Colors.with_opacity(0.12, ft.Colors.BLACK),
            offset=ft.Offset(0, 2),
        ),
    )

    log_header = ft.Text(
        "Log Output",
        theme_style=ft.TextThemeStyle.TITLE_SMALL,
        color="#0D1B3E",
        weight=ft.FontWeight.W_600,
        font_family="Century Gothic Bold",
    )

    body = ft.Column(
        [form, log_header, log_container],
        expand=True,
        spacing=12,
    )

    page.add(
        ft.Container(
            content=body,
            padding=ft.padding.all(28),
            expand=True,
        ),
    )


def run_ui() -> None:
    ft.run(main_page)


if __name__ == "__main__":
    run_ui()
