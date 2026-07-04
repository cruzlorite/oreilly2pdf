"""Selenium-based browser for rendering O'Reilly chapters to PDF."""

from __future__ import annotations

import base64
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from oreilly2pdf.api import Chapter


# ---------------------------------------------------------------------------
# JavaScript: scroll, force-load, and wait for every image in the article
# ---------------------------------------------------------------------------
SCROLL_AND_WAIT_IMAGES_JS = """
return await new Promise((resolve) => {
    // 1. Force all lazy-loaded images to eager and copy data-src → src
    const article = document.querySelector('#content-panel > section > article');
    const scope = article || document;
    scope.querySelectorAll('img').forEach(img => {
        img.loading = 'eager';
        if (!img.getAttribute('src') && img.getAttribute('data-src')) {
            img.src = img.getAttribute('data-src');
        }
    });

    // 2. Scroll to bottom in steps to trigger viewport-based lazy loaders
    const scrollStep = window.innerHeight;
    const maxScroll = document.body.scrollHeight;
    let pos = 0;

    function doScroll() {
        if (pos < maxScroll) {
            pos += scrollStep;
            window.scrollTo(0, pos);
            setTimeout(doScroll, 80);
        } else {
            window.scrollTo(0, 0);
            waitForImages();
        }
    }

    function waitForImages() {
        const imgs = scope.querySelectorAll('img');
        if (imgs.length === 0) { resolve(0); return; }

        // Poll-based: wait until every image is complete (loaded or errored)
        const deadline = Date.now() + 45000;

        function poll() {
            let pending = 0;
            imgs.forEach(img => {
                if (!img.complete) pending++;
            });
            if (pending === 0 || Date.now() > deadline) {
                let loaded = 0;
                imgs.forEach(img => { if (img.complete && img.naturalWidth > 0) loaded++; });
                resolve(loaded);
            } else {
                setTimeout(poll, 200);
            }
        }
        poll();
    }

    doScroll();
});
"""

# ---------------------------------------------------------------------------
# JavaScript: resolve relative img URLs and wait for any broken images
# This runs AFTER the article has been re-attached to the body.
# ---------------------------------------------------------------------------
RESOLVE_AND_RELOAD_IMAGES_JS = """
return await new Promise((resolve) => {
    const imgs = document.querySelectorAll('img');
    if (imgs.length === 0) { resolve(0); return; }

    // Find images that are broken (complete but naturalWidth === 0) or
    // still loading after we detached/re-attached.
    const broken = [];
    imgs.forEach(img => {
        // Ensure src attribute is the absolute URL
        if (img.src) img.setAttribute('src', img.src);
        if (!img.complete || img.naturalWidth === 0) {
            broken.push(img);
        }
    });

    if (broken.length === 0) { resolve(0); return; }

    let remaining = broken.length;
    const done = () => { remaining--; if (remaining <= 0) resolve(broken.length); };

    broken.forEach(img => {
        const src = img.getAttribute('src');
        img.addEventListener('load', done, {once: true});
        img.addEventListener('error', done, {once: true});
        // Force re-fetch by cycling the src
        img.removeAttribute('src');
        img.setAttribute('src', src);
    });

    setTimeout(() => resolve(broken.length - remaining), 30000);
});
"""


def _build_cleanup_js(book_id: str, chapter_filenames: list[str]) -> str:
    """Build the JS cleanup script.

    - Resolves all relative image URLs to absolute BEFORE detaching from DOM.
    - Strips the page down to the article content only.
    - Removes all fixed/sticky overlays, popups, and cookie banners.
    - Rewrites internal O'Reilly hyperlinks to ``#filename`` fragment anchors.
    """
    filenames_js = ", ".join(f"'{f}'" for f in chapter_filenames)

    return (
        """
(function() {
    const bookId = '"""
        + book_id
        + """';
    const knownFiles = ["""
        + filenames_js
        + """];

    const content = document.querySelector('#content-panel > section > article');
    if (!content) return;

    // ---- Resolve all relative image URLs to absolute BEFORE detaching ----
    content.querySelectorAll('img[src]').forEach(img => {
        img.setAttribute('src', img.src);  // img.src is always absolute
    });
    content.querySelectorAll('[srcset]').forEach(el => {
        el.setAttribute('srcset', el.srcset);
    });

    // ---- Remove O'Reilly reading UI widgets from inside the article ----
    // These are fixed/sticky sidebar menus, icon panels, and overlays
    // that the SPA injects into the article DOM.
    content.querySelectorAll('*').forEach(el => {
        try {
            const s = window.getComputedStyle(el);
            if (s.position === 'fixed' || s.position === 'sticky') {
                el.remove();
            }
        } catch(e) {}
    });

    // ---- Replace body with just the article content ----
    document.body.innerHTML = '';
    document.body.appendChild(content);

    // ---- Remove any remaining fixed/sticky overlays ----
    // After replacing body, scripts may still inject elements.
    // Remove everything from body that isn't our content.
    Array.from(document.body.children).forEach(el => {
        if (el !== content) el.remove();
    });

    // Remove fixed/sticky elements that live outside body (e.g. in <html>)
    document.querySelectorAll('*').forEach(el => {
        if (el === document.documentElement || el === document.head ||
            el === document.body || el === content || content.contains(el) ||
            el.tagName === 'STYLE' || el.tagName === 'LINK' || el.tagName === 'META' ||
            el.tagName === 'TITLE') return;
        try {
            const s = window.getComputedStyle(el);
            if (s.position === 'fixed' || s.position === 'sticky') {
                el.remove();
            }
        } catch(e) {}
    });
    // Nuke known O'Reilly UI ids
    ['onetrust-banner-sdk', 'onetrust-pc-sdk', 'sec-overlay',
     'orm-global-site-header', 'content-navigation'
    ].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.remove();
    });

    // Kill all running scripts / observers that could re-inject UI
    // by removing all script tags except inline style
    document.querySelectorAll('script').forEach(s => s.remove());

    // Get the current chapter filename for link rewriting
    const currentFile = location.pathname.split('/').pop();

    // ---- Ensure every id becomes a PDF named destination ----
    // Chrome only creates named destinations for elements that are link
    // targets.  We insert a hidden self-referencing <a href="#id"> for
    // each id so that the post-merge step can resolve cross-chapter links.
    content.querySelectorAll('[id]').forEach(el => {
        const a = document.createElement('a');
        a.href = '#' + el.id;
        a.style.display = 'none';
        a.textContent = '.';
        el.appendChild(a);
    });

    // ---- Create a named destination for the chapter itself ----
    // Links from the TOC or introduction that point to a chapter file
    // without a #fragment (e.g. ".../c15.xhtml") need a destination at
    // the top of that chapter.  We use the convention "_chapter_<filename>".
    const chapterAnchor = document.createElement('a');
    chapterAnchor.id = '_chapter_' + currentFile;
    chapterAnchor.href = '#_chapter_' + currentFile;
    chapterAnchor.style.display = 'none';
    chapterAnchor.textContent = '.';
    content.prepend(chapterAnchor);

    // ---- Rewrite internal hyperlinks to fragment-only anchors ----
    // Links pointing to the SAME chapter become #fragment links so Chrome
    // resolves them within the PDF.  Links to OTHER chapters are left as
    // full URIs so that the post-merge step in pdf.py can convert them
    // to GoTo named-destination links.
    document.querySelectorAll('a[href]').forEach(a => {
        const href = a.getAttribute('href');
        for (const fname of knownFiles) {
            if (href.includes(bookId + '/' + fname) || href.endsWith('/' + fname)) {
                if (fname === currentFile) {
                    // Same chapter → use fragment anchor
                    const hash = href.includes('#') ? href.split('#')[1] : fname;
                    a.setAttribute('href', '#' + hash);
                }
                // Cross-chapter links are left as-is (full URIs)
                break;
            }
        }
    });

    // ---- Minimal print CSS — keep O'Reilly original styling intact ----
    const style = document.createElement('style');
    style.textContent = `
        @page { margin: 1.5cm; }
        body { margin: 0; padding: 20px 40px; background: #fff; }
        img { max-width: 100%; height: auto; }
    `;
    document.head.appendChild(style);
})();
"""
    )


def _make_driver() -> webdriver.Chrome:
    """Create a headless Chrome WebDriver configured for PDF printing."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--run-all-compositor-stages-before-draw")
    options.add_argument("--window-size=1280,4096")
    driver = webdriver.Chrome(options=options)
    driver.set_script_timeout(120)  # allow long image-wait scripts
    return driver


def _set_cookies(driver: webdriver.Chrome, cookie_string: str) -> None:
    """Inject session cookies into the browser."""
    # Must first navigate to the domain so cookies can be set
    driver.get("https://learning.oreilly.com")
    time.sleep(1)
    for pair in cookie_string.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        name, value = pair.split("=", maxsplit=1)
        driver.add_cookie(
            {
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".oreilly.com",
            }
        )


def _print_to_pdf(driver: webdriver.Chrome) -> bytes:
    """Use Chrome DevTools Protocol to print the current page to PDF."""
    result = driver.execute_cdp_cmd(
        "Page.printToPDF",
        {
            "printBackground": True,
            "preferCSSPageSize": True,
            "marginTop": 0,
            "marginBottom": 0,
            "marginLeft": 0,
            "marginRight": 0,
        },
    )
    return base64.b64decode(result["data"])


def render_chapters(
    chapters: list[Chapter],
    cookie_string: str,
    output_dir: Path,
    *,
    book_id: str = "",
    all_filenames: list[str] | None = None,
    page_load_wait: float = 10,
    on_progress: callable | None = None,
) -> list[Path]:
    """Render each chapter to a PDF file.

    Parameters
    ----------
    chapters:
        Ordered list of chapters to render.
    cookie_string:
        Session cookies string.
    output_dir:
        Directory to write individual chapter PDFs.
    book_id:
        The book identifier, used for rewriting internal links.
    all_filenames:
        Complete list of filenames in the book spine, used for link
        rewriting.  If *None*, links are not rewritten.
    page_load_wait:
        Seconds to wait for page content to load.
    on_progress:
        Optional callback ``(index, total, chapter)`` for progress reporting.

    Returns
    -------
    list[Path]
        Ordered list of generated PDF file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    driver = _make_driver()
    pdf_paths: list[Path] = []

    cleanup_js = _build_cleanup_js(book_id, all_filenames or [])

    try:
        _set_cookies(driver, cookie_string)

        for idx, chapter in enumerate(chapters):
            if on_progress:
                on_progress(idx, len(chapters), chapter)

            driver.get(chapter.url)

            # Wait for the chapter content to actually render inside the
            # article.  The O'Reilly SPA initially shows a "Hang tight"
            # loading message inside the article element, so we must wait
            # until that disappears and real chapter content appears.
            try:
                WebDriverWait(driver, page_load_wait).until(
                    lambda d: d.execute_script("""
                        const a = document.querySelector(
                            '#content-panel > section > article');
                        if (!a) return false;
                        const text = a.textContent;
                        if (text.includes('Hang tight')) return false;
                        return a.querySelectorAll('p').length > 5
                            || a.querySelectorAll('section').length > 3;
                    """)
                )
            except Exception:
                # Fallback: just give it some time
                time.sleep(5)

            # Scroll the page to trigger lazy-loaded images, then wait
            driver.execute_script(SCROLL_AND_WAIT_IMAGES_JS)

            # Clean up the page: keep only article, remove popups/overlays
            driver.execute_script(cleanup_js)

            # Re-fetch any images that broke during DOM detach/re-attach
            driver.execute_script(RESOLVE_AND_RELOAD_IMAGES_JS)
            time.sleep(0.3)

            # Final pass: remove any fixed/sticky elements that scripts
            # may have re-injected after cleanup
            driver.execute_script("""
                const article = document.body.firstElementChild;
                document.querySelectorAll('*').forEach(el => {
                    if (el === document.documentElement || el === document.head ||
                        el === document.body || el === article ||
                        (article && article.contains(el)) ||
                        el.tagName === 'STYLE' || el.tagName === 'LINK') return;
                    try {
                        const s = window.getComputedStyle(el);
                        if (s.position === 'fixed' || s.position === 'sticky') {
                            el.remove();
                        }
                    } catch(e) {}
                });
            """)

            # Print to PDF
            pdf_bytes = _print_to_pdf(driver)
            safe_name = chapter.filename.replace("/", "_")
            pdf_path = output_dir / f"{idx:04d}_{safe_name}.pdf"
            pdf_path.write_bytes(pdf_bytes)
            pdf_paths.append(pdf_path)

    finally:
        driver.quit()

    return pdf_paths
