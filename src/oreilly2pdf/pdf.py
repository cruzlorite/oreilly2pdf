"""Merge multiple PDF files into one and fix cross-chapter links."""

from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    DictionaryObject,
    NameObject,
    TextStringObject,
)


def _resolve_cross_chapter_links(writer: PdfWriter, book_id: str) -> int:
    """Convert URI links targeting the same book into internal GoTo links.

    After individual chapter PDFs are merged the named destinations from
    every chapter coexist in a single PDF.  This function scans all link
    annotations, finds those whose URI matches the book (contains
    *book_id*) **and** whose fragment matches a named destination, then
    rewrites them from ``/URI`` actions to ``/GoTo`` actions so the PDF
    reader jumps to the right page.

    Returns the number of links rewritten.
    """
    # Write the current state to memory, read it back to get the full
    # named destination map that pypdf builds during merge.
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    reader = PdfReader(buf)

    dest_map: dict[str, object] = {}
    for key in reader.named_destinations:
        dest_map[key.lstrip("/")] = True

    if not dest_map:
        return 0

    rewritten = 0
    for page in writer.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        for ann_ref in annots:
            ann = ann_ref.get_object()
            if str(ann.get("/Subtype")) != "/Link":
                continue
            action = ann.get("/A")
            if not action:
                continue
            action_obj = (
                action.get_object() if hasattr(action, "get_object") else action
            )
            if str(action_obj.get("/S")) != "/URI":
                continue
            uri = str(action_obj.get("/URI", ""))
            if book_id not in uri:
                continue

            if "#" in uri:
                fragment = uri.split("#", 1)[1]
            else:
                # No fragment – link targets the chapter file itself.
                # Use the convention _chapter_<filename>.
                filename = uri.rstrip("/").rsplit("/", 1)[-1]
                fragment = f"_chapter_{filename}"

            # Look up the fragment in the named destinations
            dest_key = fragment if fragment in dest_map else None
            if dest_key is None and f"R_{fragment}" in dest_map:
                dest_key = f"R_{fragment}"
            if dest_key is None:
                continue

            # Rewrite: replace /URI action with /GoTo + named destination
            ann[NameObject("/A")] = DictionaryObject(
                {
                    NameObject("/S"): NameObject("/GoTo"),
                    NameObject("/D"): TextStringObject(dest_key),
                }
            )
            rewritten += 1

    return rewritten


def merge_pdfs(
    pdf_paths: list[Path],
    output_path: Path,
    *,
    book_id: str = "",
) -> int:
    """Merge an ordered list of PDFs into a single output file.

    If *book_id* is provided, cross-chapter URI links whose fragment
    matches a named destination in the merged PDF are converted to
    internal GoTo links so they work as clickable references.

    Parameters
    ----------
    pdf_paths:
        Ordered list of PDF file paths to merge.
    output_path:
        Destination path for the merged PDF.
    book_id:
        The book identifier used to recognise internal links.

    Returns
    -------
    int
        Number of cross-chapter links resolved.
    """
    writer = PdfWriter()
    for pdf_path in pdf_paths:
        writer.append(str(pdf_path))

    n_fixed = 0
    if book_id:
        n_fixed = _resolve_cross_chapter_links(writer, book_id)

    with open(output_path, "wb") as fh:
        writer.write(fh)
    writer.close()
    return n_fixed
