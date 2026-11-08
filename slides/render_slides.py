#!/usr/bin/env python
# Render slides.html -> slides.pdf (one 16:9 page per section) + cover.png (1920x1080).
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
HTML = (HERE / "slides.html").resolve().as_uri()

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(HTML, wait_until="networkidle")

    # PDF: honour the CSS @page size (1280x720 px -> true 16:9), no extra margins.
    page.emulate_media(media="print")
    page.pdf(path=str(HERE / "slides.pdf"),
             prefer_css_page_size=True, print_background=True)

    # Cover PNG at 1920x1080 (2x scale of the 1280x720 first slide for crisp text).
    cover = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
    cover.goto(HTML, wait_until="networkidle")
    cover.locator("section.slide").first.screenshot(path=str(HERE / "cover.png"))

    browser.close()
print("DONE_SLIDES")
