# 📚 oreilly2pdf

[![PyPI version](https://img.shields.io/pypi/v/oreilly2pdf?color=blue)](https://pypi.org/project/oreilly2pdf/)
[![Python versions](https://img.shields.io/pypi/pyversions/oreilly2pdf)](https://pypi.org/project/oreilly2pdf/)
[![License: MIT](https://img.shields.io/github/license/cruzlorite/oreilly2pdf)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/cruzlorite/oreilly2pdf?style=social)](https://github.com/cruzlorite/oreilly2pdf)

**Download any book from [O'Reilly Learning](https://learning.oreilly.com) as a single, high-quality PDF — perfect for offline reading.**

All images, cross-chapter links, table of contents, and index entries just work — exactly as you'd expect from a real book.

> ⚠️ Requires an active O'Reilly Learning subscription.

---

## ⚡ Quick Start

```bash
pip install oreilly2pdf
oreilly2pdf 9781098150952 --cookie-file cookies.json
```

That's it. You'll get a `9781098150952.pdf` with all chapters merged into one file.

---

## 🔧 Installation

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

### Requirements

- Python 3.10+
- Google Chrome (or Chromium)
- ChromeDriver — installed automatically by Selenium 4.20+

---

## 🍪 Getting Your Cookies

You need to provide your O'Reilly session cookies so the tool can access your account. There are three easy ways to get them:

### Way 1 — DevTools Console (fastest)

1. Log in to [learning.oreilly.com](https://learning.oreilly.com) in Chrome.
2. Open DevTools (`F12`) → go to the **Console** tab.
3. Paste this and press Enter:

```js
copy(JSON.stringify(Object.fromEntries(document.cookie.split('; ').map(c => c.split('=')))))
```

4. Your cookies are now in the clipboard. Save them to a file:

```bash
pbpaste > cookies.json   # macOS
xclip -o > cookies.json  # Linux
```

### Way 2 — Cookie-Editor extension

1. Install [Cookie-Editor](https://cookie-editor.com) in your browser.
2. Go to [learning.oreilly.com](https://learning.oreilly.com) and log in.
3. Click the Cookie-Editor icon → **Export** → **JSON**.
4. Paste into `cookies.json` and reformat as `{"name": "value"}` pairs.

### Way 3 — Manual

1. Open DevTools (`F12`) → **Application** tab → **Cookies** → `https://learning.oreilly.com`.
2. Create a `cookies.json` with the relevant cookie values:

```json
{
  "BrowserCookie": "...",
  "orm-jwt": "...",
  "orm-rt": "...",
  "groot_sessionid": "..."
}
```

> **Note**: The most important cookies are typically `orm-jwt` and `groot_sessionid`. If export fails, try adding more cookies from your browser.

---

## 📖 Finding the Book ID

Open any book on O'Reilly and look at the URL — the book ID is the ISBN number:

```
https://learning.oreilly.com/library/view/book-title/9781098150952/
                                                     ^^^^^^^^^^^^^
                                                        book_id
```

---

## 🚀 Usage

```bash
# Basic usage
oreilly2pdf <book_id> --cookie-file cookies.json

# Custom output filename
oreilly2pdf 9781098150952 --cookie-file cookies.json -o my_book.pdf

# Inline cookies instead of a file
oreilly2pdf 9781098150952 --cookies "orm-jwt=eyJ...; groot_sessionid=xyz"

# Keep individual chapter PDFs alongside the merged output
oreilly2pdf 9781098150952 --cookie-file cookies.json --keep-chapters
```

### All Options

| Option | Description |
|---|---|
| `book_id` | O'Reilly book identifier (ISBN) — **required** |
| `--cookie-file FILE` | Path to a cookies file (JSON or plain text) |
| `--cookies STRING` | Inline cookies (`key=value; key2=value2`) |
| `-o, --output FILE` | Output path (default: `<book_id>.pdf`) |
| `--keep-chapters` | Save individual chapter PDFs too |

---

## ✨ Features

| | |
|---|---|
| 📄 **Full book** | Cover, TOC, all chapters, appendices, index — everything |
| 🖼️ **Images** | Lazy-loaded and dynamic images fully resolved |
| �� **Cross-chapter links** | "See Section 4.3" actually jumps to Section 4.3 |
| 🧹 **Clean output** | No navigation bars, cookie banners, or popups |
| 🎨 **Faithful rendering** | Math, code blocks, tables, figures — pixel-perfect |

---

## 🔍 How It Works

1. Fetches the book's table of contents from the O'Reilly API.
2. Opens each chapter in headless Chrome with your session cookies.
3. Waits for all images (including lazy-loaded ones) to fully render.
4. Strips the O'Reilly UI — keeps only the book content.
5. Prints each chapter to PDF via Chrome DevTools Protocol.
6. Merges everything into a single PDF and rewrites cross-chapter links so they work as clickable in-document jumps.

---

## ⚖️ Disclaimer

This tool is intended for **personal, offline use only** by users who hold a valid O'Reilly Learning subscription. It accesses content you are already entitled to read through your account.

- **Do not** distribute, share, or upload exported PDFs.
- **Do not** use this tool to circumvent access controls or pirate content.
- You are solely responsible for complying with O'Reilly's [Terms of Service](https://www.oreilly.com/terms/) and applicable copyright law.

The authors of this project are not affiliated with O'Reilly Media and assume no liability for misuse.

---

## 🙏 Acknowledgements

Inspired by [oreilly-epub-downloader](https://github.com/tctibbs/oreilly-epub-downloader) by [@tctibbs](https://github.com/tctibbs).

## 📄 License

[MIT](LICENSE)
