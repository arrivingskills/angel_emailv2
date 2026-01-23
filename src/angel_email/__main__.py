from __future__ import annotations

# Allow running this file directly from a fresh source checkout (src/ layout)
try:
    from angel_email import main  # type: ignore
except Exception:  # pragma: no cover - best-effort import shim for local runs
    import sys
    from pathlib import Path

    # Add the parent "src" directory to PYTHONPATH
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from angel_email import main  # type: ignore


if __name__ == "__main__":
    main()
