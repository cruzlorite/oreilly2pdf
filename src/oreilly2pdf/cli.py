"""Command-line interface for oreilly2pdf."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from oreilly2pdf.api import get_book
from oreilly2pdf.browser import render_chapters
from oreilly2pdf.pdf import merge_pdfs


def _resolve_cookies(args: argparse.Namespace) -> str:
    """Return the cookie string from either --cookies or --cookie-file.

    Supports both plain text files (``key=value; ...``) and JSON files
    (``{"key": "value", ...}``).
    """
    if args.cookies:
        return args.cookies
    cookie_path = Path(args.cookie_file)
    if not cookie_path.is_file():
        print(f"Error: cookie file not found: {cookie_path}", file=sys.stderr)
        sys.exit(1)
    raw = cookie_path.read_text().strip()
    # Try to parse as JSON
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return "; ".join(f"{k}={v}" for k, v in data.items())
    except (json.JSONDecodeError, ValueError):
        pass
    # Otherwise treat as plain semicolon-separated string
    return raw


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="oreilly2pdf",
        description="Export O'Reilly books as PDF.",
    )
    parser.add_argument(
        "book_id",
        help="The O'Reilly book identifier (ISBN).",
    )

    cookie_group = parser.add_mutually_exclusive_group(required=True)
    cookie_group.add_argument(
        "--cookies",
        default=None,
        help="Session cookies as 'key=value' pairs separated by semicolons.",
    )
    cookie_group.add_argument(
        "--cookie-file",
        default=None,
        help=(
            'Path to a cookies file. Accepts JSON ({"key": "value"}) '
            "or plain text (key=value; key2=value2)."
        ),
    )

    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output PDF file path (default: <book_id>.pdf).",
    )
    parser.add_argument(
        "--keep-chapters",
        action="store_true",
        default=False,
        help="Keep individual chapter PDFs in a directory alongside the output.",
    )
    return parser.parse_args(argv)


def _progress(index: int, total: int, chapter) -> None:  # noqa: ANN001
    """Print progress to stderr."""
    pct = (index + 1) / total * 100
    print(
        f"  [{index + 1}/{total}] ({pct:5.1f}%) {chapter.title}",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> None:
    """Entry point for the CLI."""
    args = parse_args(argv)

    book_id: str = args.book_id
    cookies: str = _resolve_cookies(args)
    output: str = args.output or f"{book_id}.pdf"
    output_path = Path(output)

    # --- 1. Fetch book metadata + chapter list ---
    print(f"Fetching book metadata for {book_id} ...", file=sys.stderr)
    book = get_book(book_id, cookies)
    print(f"Book    : {book.title}", file=sys.stderr)
    print(f"Chapters: {len(book.chapters)}", file=sys.stderr)

    all_filenames = [ch.filename for ch in book.chapters]

    # --- 2. Render each chapter to PDF via headless Chrome ---
    tmp_dir = Path(tempfile.mkdtemp(prefix="oreilly2pdf_"))
    try:
        print("Rendering chapters …", file=sys.stderr)
        pdf_paths = render_chapters(
            book.chapters,
            cookies,
            tmp_dir,
            book_id=book_id,
            all_filenames=all_filenames,
            on_progress=_progress,
        )

        # --- 3. Merge chapter PDFs + resolve cross-chapter links ---
        print(f"Merging {len(pdf_paths)} PDFs → {output_path} …", file=sys.stderr)
        n_fixed = merge_pdfs(pdf_paths, output_path, book_id=book_id)
        if n_fixed:
            print(f"Resolved {n_fixed} cross-chapter links.", file=sys.stderr)
        print(f"Done! Saved to {output_path}", file=sys.stderr)

        # Optionally keep individual chapter PDFs
        if args.keep_chapters:
            chapters_dir = output_path.with_suffix("") / "chapters"
            chapters_dir.mkdir(parents=True, exist_ok=True)
            for p in pdf_paths:
                shutil.copy2(p, chapters_dir / p.name)
            print(
                f"Chapter PDFs saved to {chapters_dir}",
                file=sys.stderr,
            )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
