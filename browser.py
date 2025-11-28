from typing import List, Dict, Any
from playwright.sync_api import sync_playwright


def fetch_quiz_page(url: str) -> Dict[str, Any]:
    """
    Fetch the quiz page HTML, body text, and links using Playwright.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")

            body_text = page.inner_text("body")

            links: List[Dict[str, str]] = page.eval_on_selector_all(
                "a",
                "els => els.map(e => ({href: e.href, text: e.textContent}))",
            )
        finally:
            browser.close()

    return {
        "url": url,
        "body_text": body_text,
        "links": links,
    }
