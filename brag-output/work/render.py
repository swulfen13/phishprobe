#!/usr/bin/env python
# Render video.html to a PNG frame sequence by stepping the seek(t) timeline.
# 52s timeline @ 30fps = 1560 frames; frame N -> t = (N-1)/30.
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
HTML = (HERE / "video.html").resolve().as_uri()
FRAMES = HERE / "frames"
FRAMES.mkdir(exist_ok=True)

FPS = 30
DURATION = 52.0
N = int(round(FPS * DURATION))  # 1560

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--force-color-profile=srgb"])
    page = browser.new_page(viewport={"width": 1920, "height": 1080},
                            device_scale_factor=1)
    page.goto(HTML)
    page.wait_for_function("typeof window.seek === 'function'")
    for i in range(N):
        t = i / FPS
        page.evaluate("(t) => window.seek(t)", t)
        out = FRAMES / f"frame_{i+1:04d}.png"
        page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": 1920, "height": 1080})
        if (i + 1) % 100 == 0:
            print(f"  rendered {i+1}/{N}", flush=True)
    browser.close()
print("DONE_RENDER")
