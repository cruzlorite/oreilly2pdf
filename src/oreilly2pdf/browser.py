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
return new Promise((resolve) => {
    const article = document.querySelector('#content-panel > section > article');
    const scope = article || document;

    // Force eager loading + fix lazy images
    scope.querySelectorAll('img').forEach(img => {
        img.loading = 'eager';
        if (!img.getAttribute('src') && img.getAttribute('data-src')) {
            img.src = img.getAttribute('data-src');
        }
    });

    // Deterministic scroll (NO scrollHeight dependency)
    let steps = 0;
    const maxSteps = 25;

    function step() {
        window.scrollTo(0, document.body.scrollHeight);

        steps++;

        if (steps >= maxSteps) {
            waitForImages();
            return;
        }

        setTimeout(step, 300);
    }

    function waitForImages() {
        const imgs = scope.querySelectorAll('img');

        if (imgs.length === 0) {
            resolve(0);
            return;
        }

        const deadline = Date.now() + 30000;

        function poll() {
            let pending = 0;

            imgs.forEach(img => {
                if (!img.complete) pending++;
            });

            if (pending === 0 || Date.now() > deadline) {
                let loaded = 0;

                imgs.forEach(img => {
                    if (img.complete && img.naturalWidth > 0) loaded++;
                });

                resolve(loaded);
            } else {
                setTimeout(poll, 200);
            }
        }

        poll();
    }

    step();
});
"""


# ---------------------------------------------------------------------------
# JavaScript: resolve relative img URLs and retry broken images
# ---------------------------------------------------------------------------
RESOLVE_AND_RELOAD_IMAGES_JS = """
return new Promise((resolve) => {
    const imgs = document.querySelectorAll('img');

    if (imgs.length === 0) {
        resolve(0);
        return;
    }

    const broken = [];

    imgs.forEach(img => {
        if (img.src) img.setAttribute('src', img.src);

        if (!img.complete || img.naturalWidth === 0) {
            broken.push(img);
        }
    });

    if (broken.length === 0) {
        resolve(0);
        return;
    }

    let remaining = broken.length;

    const done = () => {
        remaining--;
        if (remaining <= 0) resolve(broken.length);
    };

    broken.forEach(img => {
        const src = img.getAttribute('src');

        img.addEventListener('load', done, { once: true });
        img.addEventListener('error', done, { once: true });

        img.removeAttribute('src');
        img.setAttribute('src', src);
    });

    setTimeout(() => {
        resolve(broken.length - remaining);
    }, 30000);
});
"""


def _build_cleanup_js(book_id: str, chapter_filenames: list[str]) -> str:
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

    // Resolve images BEFORE DOM rewrite
    content.querySelectorAll('img[src]').forEach(img => {
        img.setAttribute('src', img.src);
    });

    content.querySelectorAll('[srcset]').forEach(el => {
        el.setAttribute('srcset', el.srcset);
    });

    // Remove fixed/sticky UI inside article
    content.querySelectorAll('*').forEach(el => {
        try {
            const s = window.getComputedStyle(el);
            if (s.position === 'fixed' || s.position === 'sticky') {
                el.remove();
            }
        } catch (e) {}
    });

    // Replace body with article
    document.body.innerHTML = '';
    document.body.appendChild(content);

    // Cleanup leftovers
    Array.from(document.body.children).forEach(el => {
        if (el !== content) el.remove();
    });

    // Remove global overlays
    document.querySelectorAll('*').forEach(el => {
        if (
            el === document.documentElement ||
            el === document.head ||
            el === document.body ||
            el === content ||
            content.contains(el) ||
            ['STYLE','LINK','META','TITLE'].includes(el.tagName)
        ) return;

        try {
            const s = window.getComputedStyle(el);
            if (s.position === 'fixed' || s.position === 'sticky') {
                el.remove();
            }
        } catch (e) {}
    });

    // Remove known O'Reilly UI
    [
        'onetrust-banner-sdk',
        'onetrust-pc-sdk',
        'sec-overlay',
        'orm-global-site-header',
        'content-navigation'
    ].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.remove();
    });

    document.querySelectorAll('script').forEach(s => s.remove());

    const currentFile = location.pathname.split('/').pop();

    // Add anchors for PDF linking
    content.querySelectorAll('[id]').forEach(el => {
        const a = document.createElement('a');
        a.href = '#' + el.id;
        a.style.display = 'none';
        a.textContent = '.';
        el.appendChild(a);
    });

    const chapterAnchor = document.createElement('a');
    chapterAnchor.id = '_chapter_' + currentFile;
    chapterAnchor.href = '#_chapter_' + currentFile;
    chapterAnchor.style.display = 'none';
    content.prepend(chapterAnchor);

    // Rewrite links
    document.querySelectorAll('a[href]').forEach(a => {
        const href = a.getAttribute('href');

        if (!href) return;

        for (const fname of knownFiles) {
            if (href.includes(bookId + '/' + fname) || href.endsWith('/' + fname)) {
                if (fname === currentFile) {
                    const hash = href.includes('#') ? href.split('#')[1] : fname;
                    a.setAttribute('href', '#' + hash);
                }
                break;
            }
        }
    });

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
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--run-all-compositor-stages-before-draw")
    options.add_argument("--window-size=1280,4096")

    driver = webdriver.Chrome(options=options)
    driver.set_script_timeout(120)
    return driver


def _set_cookies(driver: webdriver.Chrome, cookie_string: str) -> None:
    driver.get("https://learning.oreilly.com")
    time.sleep(1)

    for pair in cookie_string.split(";"):
        if "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        driver.add_cookie({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".oreilly.com",
        })


def _print_to_pdf(driver: webdriver.Chrome) -> bytes:
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

            try:
                WebDriverWait(driver, page_load_wait).until(
                    lambda d: d.execute_script("""
                        const a = document.querySelector('#content-panel > section > article');
                        if (!a) return false;
                        const text = a.textContent;
                        if (text.includes('Hang tight')) return false;
                        return a.querySelectorAll('p').length > 5
                            || a.querySelectorAll('section').length > 3;
                    """)
                )
            except Exception:
                time.sleep(5)

            driver.execute_script(SCROLL_AND_WAIT_IMAGES_JS)
            driver.execute_script(cleanup_js)
            driver.execute_script(RESOLVE_AND_RELOAD_IMAGES_JS)

            time.sleep(0.3)

            driver.execute_script("""
                const article = document.body.firstElementChild;

                document.querySelectorAll('*').forEach(el => {
                    if (
                        el === document.documentElement ||
                        el === document.head ||
                        el === document.body ||
                        el === article ||
                        (article && article.contains(el)) ||
                        ['STYLE','LINK'].includes(el.tagName)
                    ) return;

                    try {
                        const s = window.getComputedStyle(el);
                        if (s.position === 'fixed' || s.position === 'sticky') {
                            el.remove();
                        }
                    } catch (e) {}
                });
            """)

            pdf_bytes = _print_to_pdf(driver)

            safe_name = chapter.filename.replace("/", "_")
            pdf_path = output_dir / f"{idx:04d}_{safe_name}.pdf"

            pdf_path.write_bytes(pdf_bytes)
            pdf_paths.append(pdf_path)

    finally:
        driver.quit()

    return pdf_paths
