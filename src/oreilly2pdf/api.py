"""O'Reilly API v2 client for fetching book metadata and spine."""

from __future__ import annotations

from dataclasses import dataclass

import requests

BASE_URL = "https://learning.oreilly.com"
API_V2 = f"{BASE_URL}/api/v2"


@dataclass(frozen=True)
class Chapter:
    """Represents a single content file in the book spine."""

    ourn: str
    title: str
    reference_id: str
    filename: str
    url: str

    @classmethod
    def from_spine_entry(cls, entry: dict, book_id: str) -> Chapter:
        """Build a Chapter from a spine API response entry."""
        reference_id: str = entry["reference_id"]
        # reference_id format: "{book_id}-/{filename}"
        filename = reference_id.split("-/", maxsplit=1)[1]
        content_url = f"{BASE_URL}/library/view/-/{book_id}/{filename}"
        return cls(
            ourn=entry["ourn"],
            title=entry["title"],
            reference_id=reference_id,
            filename=filename,
            url=content_url,
        )


@dataclass(frozen=True)
class BookMeta:
    """High-level metadata for a book."""

    book_id: str
    title: str
    chapters: list[Chapter]


def _parse_cookies(cookie_string: str) -> dict[str, str]:
    """Parse a semicolon-separated cookie string into a dict."""
    cookies: dict[str, str] = {}
    for pair in cookie_string.split(";"):
        pair = pair.strip()
        if "=" in pair:
            key, value = pair.split("=", maxsplit=1)
            cookies[key.strip()] = value.strip()
    return cookies


def _fetch_all_spine(
    book_id: str, session: requests.Session
) -> list[dict]:
    """Fetch all spine entries, following pagination."""
    url: str | None = (
        f"{API_V2}/epubs/urn:orm:book:{book_id}/spine/"
    )
    entries: list[dict] = []
    while url is not None:
        resp = session.get(url)
        resp.raise_for_status()
        data = resp.json()
        entries.extend(data["results"])
        url = data.get("next")
    return entries


def get_book(book_id: str, cookie_string: str) -> BookMeta:
    """Fetch book metadata and the full ordered chapter list.

    Parameters
    ----------
    book_id:
        The ISBN / O'Reilly book identifier (e.g. ``"9781119024842"``).
    cookie_string:
        Session cookies as ``"key=value; key2=value2"`` string.

    Returns
    -------
    BookMeta
        Book title and an ordered list of :class:`Chapter` objects.
    """
    session = requests.Session()
    session.cookies.update(_parse_cookies(cookie_string))
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }
    )

    # 1. Book metadata
    meta_url = f"{API_V2}/epubs/urn:orm:book:{book_id}/"
    meta_resp = session.get(meta_url)
    meta_resp.raise_for_status()
    meta = meta_resp.json()
    title: str = meta["title"]

    # 2. Full spine (paginated)
    spine_entries = _fetch_all_spine(book_id, session)
    chapters = [
        Chapter.from_spine_entry(entry, book_id)
        for entry in spine_entries
    ]

    return BookMeta(book_id=book_id, title=title, chapters=chapters)
