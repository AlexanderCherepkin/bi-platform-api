#!/usr/bin/env python3
"""Headless browser screenshot regression for the BI Next.js app.

Implements the tools_browser/headless_automation pipeline contract for this
project: batch navigation and screenshot capture across mobile/tablet/desktop
viewports, with JWT auth via localStorage.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright, Page

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = str(PROJECT_ROOT)
DEFAULT_BASE_URL = "http://localhost:3000"
DEFAULT_API_URL = "http://localhost:8000"
CREDENTIALS = {"username": "admin", "password": "admin123"}

PAGES = [
    "dashboard",
    "managers",
    "sales-funnel",
    "pnl-waterfall",
    "budget-vs-actual",
    "db-overview",
    "db-overview/transactions",
    "db-overview/public/fact_transactions",
    "sql-query",
    "embedded-reports",
    "data-input",
    "alerts",
]

VIEWPORTS = {
    "mobile": {"width": 390, "height": 844},
    "tablet": {"width": 768, "height": 1024},
    "desktop": {"width": 1600, "height": 1000},
}


def _get_token(api_url: str) -> str:
    data = urlencode(CREDENTIALS).encode()
    req = Request(f"{api_url}/api/auth/token", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())["access_token"]


def _login(page: Page, base_url: str, token: str) -> None:
    page.goto(f"{base_url}/login", wait_until="domcontentloaded", timeout=30000)
    page.evaluate(f"localStorage.setItem('bi_access_token', '{token}')")
    page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("h1", timeout=10000)


def _safe_filename(page_path: str) -> str:
    return page_path.replace("/", "_")


def _capture(page: Page, page_path: str, viewport: str, out_dir: Path) -> Path:
    safe_name = _safe_filename(page_path)
    screenshot_path = out_dir / viewport / f"{safe_name}.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot_path), full_page=True)
    return screenshot_path


def run(base_url: str, api_url: str, out_dir: Path, pages: list[str] | None = None) -> list[Path]:
    targets = pages or PAGES
    token = _get_token(api_url)
    captured: list[Path] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for viewport_name, size in VIEWPORTS.items():
                context = browser.new_context(viewport=size)
                page = context.new_page()
                _login(page, base_url, token)
                # Capture home once per viewport
                home_path = _capture(page, "home", viewport_name, out_dir)
                captured.append(home_path)
                print(f"Captured {home_path}")

                for page_path in targets:
                    url = f"{base_url}/{page_path}"
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1500)
                    path = _capture(page, page_path, viewport_name, out_dir)
                    captured.append(path)
                    print(f"Captured {path}")

                context.close()
        finally:
            browser.close()

    return captured


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture BI app screenshots across viewports.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--out-dir", type=str, default=str(PROJECT_ROOT / "bi_platform" / "screenshots"))
    parser.add_argument("--pages", type=str, default=None, help="Comma-separated list of page paths")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    pages = args.pages.split(",") if args.pages else None

    try:
        captured = run(args.base_url, args.api_url, out_dir, pages)
        print(f"\nCaptured {len(captured)} screenshots to {out_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
