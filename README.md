# oreilly2pdf

Export [O'Reilly Learning](https://learning.oreilly.com) books as high-quality PDFs with working images, table of contents, and cross-chapter hyperlinks.

## Features

- **Full book export** — cover, chapters, appendices, index, and all front/back matter.
- **High-fidelity rendering** — uses headless Chrome to capture the exact same layout you see in the browser, including mathematical equations, code blocks, tables, and figures.
- **Images** — lazy-loaded and dynamically-rendered images are fully resolved before printing.
- **Cross-chapter links** — internal references (e.g., "see Section 4.3", bibliography citations, index entries) are converted into clickable PDF links that jump to the correct page.
- **Clean output** — O'Reilly's navigation UI, cookie banners, sidebar menus, and overlays are stripped, leaving only the book content.

## Prerequisites

- **Python 3.10+**
- **Google Chrome** (or Chromium) installed
- **ChromeDriver** matching your Chrome version — installed automatically by Selenium 4.20+
- A valid **O'Reilly Learning** subscription

## Installation

### From PyPI

```bash
pip install oreilly2pdf
```

### From source

```bash
git clone https://github.com/cruzlorite/oreilly2pdf.git
cd oreilly2pdf
pip install .
```

## Usage

```bash
# Using a cookies file (recommended)
oreilly2pdf 9781098150952 --cookie-file cookies.json

# Using inline cookies
oreilly2pdf 9781098150952 --cookies "BrowserCookie=abc123; logged_in=1; ..."

# Custom output path
oreilly2pdf 9781098150952 --cookie-file cookies.json -o my_book.pdf

# Keep individual chapter PDFs
oreilly2pdf 9781098150952 --cookie-file cookies.json --keep-chapters
```

### Options

| Flag | Description |
|---|---|
| `book_id` | The O'Reilly book identifier (ISBN). |
| `--cookies` | Session cookies as `key=value` pairs separated by semicolons. |
| `--cookie-file` | Path to a cookies file (JSON or plain text). |
| `-o, --output` | Output PDF file path (default: `<book_id>.pdf`). |
| `--keep-chapters` | Keep individual chapter PDFs in a directory alongside the output. |

## Getting Your Cookies

`oreilly2pdf` needs your O'Reilly session cookies to authenticate. Here's how to get them:

### Option 1 — JSON file (recommended)

1. Log in to [learning.oreilly.com](https://learning.oreilly.com) in Chrome.
2. Open DevTools (`F12`) → **Application** tab → **Cookies** → `https://learning.oreilly.com`.
3. Create a JSON file with the cookie name/value pairs:

```json
{
  "BrowserCookie": "your_value_here",
  "logged_in": "1",
  "orm-jwt": "your_jwt_token",
  "orm-rt": "your_refresh_token",
  "groot_sessionid": "your_session_id"
}
```

The exact cookies needed may vary, but `orm-jwt` and `groot_sessionid` are typically the most important. If export fails with authentication errors, try adding more cookies from your browser.

> **Tip — browser console**: You can also grab all cookies at once by running this in the DevTools **Console** while on `learning.oreilly.com`:
>
> ```js
> JSON.stringify(Object.fromEntries(document.cookie.split('; ').map(c => c.split('='))))
> ```
>
> Copy the output and save it as `cookies.json`.

> **Tip — extension**: The [Cookie-Editor](https://cookie-editor.com) browser extension can export all cookies as JSON with one click. Export as JSON, keep only the `learning.oreilly.com` entries, and reformat as `{"name": "value"}` pairs.

4. Save as `cookies.json` and pass it with `--cookie-file cookies.json`.

### Option 2 — Plain text

Copy cookies as a semicolon-separated string:

```bash
oreilly2pdf 9781098150952 --cookies "BrowserCookie=abc; orm-jwt=eyJ...; groot_sessionid=xyz"
```

## Finding the Book ID

The book ID is the ISBN that appears in the O'Reilly URL:

```
https://learning.oreilly.com/library/view/book-title/9781098150952/
                                                     ^^^^^^^^^^^^^
                                                     This is the book_id
```

## How It Works

1. **Fetches the book spine** from the O'Reilly API to get an ordered list of all content files (cover, chapters, appendices, index, etc.).
2. **Renders each chapter** in headless Chrome with your session cookies.
3. **Waits for all images** to fully load (handles lazy-loading, viewport-triggered loading, and dynamic image injection).
4. **Cleans the page** — removes the O'Reilly reading UI (header, sidebar, navigation, cookie banners, overlays) and keeps only the article content.
5. **Creates PDF named destinations** for every element with an `id` attribute, enabling cross-chapter link resolution.
6. **Prints each chapter to PDF** using the Chrome DevTools Protocol.
7. **Merges all chapter PDFs** into a single file and rewrites internal URI links as PDF GoTo links, so cross-chapter references, index entries, and bibliography citations all work as clickable links.

## Acknowledgements

Inspired by [oreilly-epub-downloader](https://github.com/tctibbs/oreilly-epub-downloader) by [@tctibbs](https://github.com/tctibbs).

## License

[MIT](LICENSE)
