"""Exercise real Chromium upload, inference queue, overlay and review; use --url for actual models."""

import argparse
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from PIL import Image
from playwright.sync_api import expect, sync_playwright


def exercise(address, output, image=None):
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=1)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(address)
        page.get_by_role("button", name="New inspection", exact=True).click()
        page.get_by_label("Batch name").fill("Browser walkthrough")
        if image:
            page.get_by_label("Choose surface images").set_input_files(str(image))
        else:
            buffer = io.BytesIO()
            Image.new("RGB", (96, 128), "#707c72").save(buffer, format="PNG")
            page.get_by_label("Choose surface images").set_input_files(
                {
                    "name": "browser-surface.png",
                    "mimeType": "image/png",
                    "buffer": buffer.getvalue(),
                }
            )
        page.get_by_role("button", name="Inspect 1 image", exact=True).click()
        expect(page.get_by_role("dialog")).not_to_be_visible(timeout=15000)
        expect(page.get_by_text("Inspection complete", exact=True)).to_be_visible(timeout=45000)
        page.get_by_role("button", name="Anomaly map", exact=True).click()
        expect(page.locator(".image-stage img")).to_be_visible(timeout=10000)
        page.get_by_label("Review note").fill(
            "Browser workflow verification; second review requested."
        )
        page.get_by_role("button", name="Escalate for a second look").click()
        expect(page.get_by_text("Escalated", exact=True)).to_be_visible()
        # A real walkthrough captures an actual predicted anomaly, without choosing examples by test accuracy.
        if image:
            suspect = next(
                (
                    button
                    for button in page.locator(".film-card").all()
                    if button.locator(".film-dot.suspect").count()
                ),
                None,
            )
            if suspect:
                suspect.click()
        expect(page.locator(".image-stage img")).to_be_visible(timeout=10000)
        expect(page.locator(".toast")).not_to_be_visible(timeout=8000)
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(output / "inspection.png"), full_page=True)
        page.get_by_role("button", name="Review queue", exact=False).click()
        expect(page.locator("table")).to_be_visible()
        page.screenshot(path=str(output / "queue.png"))
        page.get_by_role("button", name="Model & evaluation", exact=True).click()
        if image:
            expect(page.get_by_text("The normal-reference model", exact=True)).to_be_visible()
        page.screenshot(path=str(output / "model.png"), full_page=True)
        page.get_by_role("button", name="Activity log", exact=True).click()
        expect(page.get_by_text("Item needs attention", exact=True).first).to_be_visible()
        phone = browser.new_page(
            viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
        )
        phone.on("pageerror", lambda e: errors.append(str(e)))
        phone.goto(address)
        expect(phone.locator(".viewer-card")).to_be_visible(timeout=15000)
        expect(phone.locator(".image-stage img")).to_be_visible(timeout=10000)
        assert phone.evaluate("document.documentElement.scrollWidth <= innerWidth")
        phone.screenshot(path=str(output / "mobile.png"), full_page=True)
        phone.get_by_role("button", name="Open navigation").click()
        phone.get_by_role("button", name="Model & evaluation", exact=True).click()
        expect(phone.get_by_role("heading", name="Know your model.")).to_be_visible()
        assert phone.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        browser.close()
    print(
        json.dumps(
            {
                "passed": True,
                "neural_backend": "Actual model at supplied URL"
                if image
                else "Explicit CI substitute",
                "checks": [
                    "upload",
                    "queue completion",
                    "image/heatmap",
                    "review and audit",
                    "desktop navigation",
                    "mobile layout",
                ],
                "uncaught_browser_errors": errors,
                "screenshots": str(output),
            }
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--screenshots", type=Path, default=Path("reports/browser"))
    args = parser.parse_args()
    if args.url:
        exercise(args.url, args.screenshots, args.image)
        return
    with tempfile.TemporaryDirectory(prefix="visionguard-browser-") as temporary:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = os.environ.copy()
        env.update(
            VISION_DATABASE_URL=f"sqlite:///{temporary}/db.sqlite",
            VISION_DATA_DIR=temporary,
            VISION_AUTH_MODE="local",
        )
        log = Path(temporary) / "server.log"
        with log.open("w") as output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "scripts.fixture_server:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                env=env,
                stdout=output,
                stderr=output,
            )
            try:
                address = f"http://127.0.0.1:{port}"
                for _ in range(100):
                    try:
                        if httpx.get(address + "/ready", timeout=1).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if process.poll() is not None:
                        raise RuntimeError(log.read_text())
                    time.sleep(0.1)
                exercise(address, args.screenshots)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
