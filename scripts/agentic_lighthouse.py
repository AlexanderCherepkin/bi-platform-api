#!/usr/bin/env python3
"""Lighthouse 100% hard-gate for the BI Next.js app.

Implements the Agentic Loop tools_lighthouse/audit pipeline for this project:
session_manager → navigation_engine → audit_runner → report_parser →
metric_guard_* → correction_prompt_builder → loop_terminator.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import requests
import websocket
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "http://localhost:3000"
DEFAULT_API_URL = "http://localhost:8000"
CREDENTIALS = {"username": "admin", "password": "admin123"}
MAX_ITERATIONS = 8

PAGES = [
    "login",
    "dashboard",
    "managers",
    "sales-funnel",
    "pnl-waterfall",
    "budget-vs-actual",
    "db-overview",
    "data-input",
    "alerts",
]


def _get_token(api_url: str) -> str:
    data = urlencode(CREDENTIALS).encode()
    req = Request(f"{api_url}/auth/token", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())["access_token"]


def _launch_chrome() -> tuple[Any, int]:
    """Launch Playwright Chromium with remote debugging and return browser + port."""
    port = 9224
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=True,
        executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        args=[
            f"--remote-debugging-port={port}",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
        ],
    )
    return playwright, browser, port


def _ws_url(port: int) -> str:
    resp = requests.get(f"http://localhost:{port}/json/version", timeout=5)
    data = resp.json()
    return data["webSocketDebuggerUrl"]


def _set_auth_token(port: int, base_url: str, token: str) -> None:
    """Set bi_access_token in localStorage via Chrome DevTools Protocol."""
    ws_url = _ws_url(port)
    ws = websocket.create_connection(ws_url, timeout=10)
    try:
        # Open a new tab for login page
        ws.send(json.dumps({"id": 1, "method": "Target.createTarget", "params": {"url": f"{base_url}/login"}}))
        resp = json.loads(ws.recv())
        target_id = resp["result"]["targetId"]

        ws.send(json.dumps({"id": 2, "method": "Target.attachToTarget", "params": {"targetId": target_id, "flatten": True}}))
        resp = json.loads(ws.recv())
        session_id = resp["result"]["sessionId"]

        # Wait for load
        ws.send(json.dumps({"id": 3, "method": "Runtime.evaluate", "sessionId": session_id, "params": {"expression": "document.readyState"}}))
        for _ in range(20):
            msg = json.loads(ws.recv())
            if msg.get("id") == 3:
                break

        # Set token
        expr = f"localStorage.setItem('bi_access_token', '{token}')"
        ws.send(json.dumps({"id": 4, "method": "Runtime.evaluate", "sessionId": session_id, "params": {"expression": expr}}))
        for _ in range(20):
            msg = json.loads(ws.recv())
            if msg.get("id") == 4:
                break

        ws.send(json.dumps({"id": 5, "method": "Target.closeTarget", "params": {"targetId": target_id}}))
        for _ in range(20):
            msg = json.loads(ws.recv())
            if msg.get("id") == 5:
                break
    finally:
        ws.close()


def _run_lighthouse(port: int, url: str, out_path: Path, form_factor: str) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    preset = "desktop" if form_factor == "desktop" else "mobile"
    cmd = [
        "npx", "lighthouse",
        url,
        f"--port={port}",
        f"--preset={preset}",
        "--output=json",
        f"--output-path={out_path}",
        "--chrome-flags=--headless --no-sandbox --disable-gpu",
        "--max-wait-for-load=45000",
    ]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT / "bi_platform" / "vercel-app", capture_output=True, text=True, timeout=120)
    if not out_path.exists():
        raise RuntimeError(f"Lighthouse did not produce report: {result.stderr}")
    return json.loads(out_path.read_text(encoding="utf-8"))


def _scores(report: dict) -> dict[str, int]:
    cats = report.get("categories", {})
    return {
        "performance": round(cats.get("performance", {}).get("score", 0) * 100),
        "accessibility": round(cats.get("accessibility", {}).get("score", 0) * 100),
        "best_practices": round(cats.get("best-practices", {}).get("score", 0) * 100),
        "seo": round(cats.get("seo", {}).get("score", 0) * 100),
    }


def _failed_audits(report: dict) -> list[dict]:
    failed = []
    for cat in report.get("categories", {}).values():
        for audit_ref in cat.get("auditRefs", []):
            audit = report.get("audits", {}).get(audit_ref["id"])
            if not audit:
                continue
            if audit.get("score") is not None and audit["score"] < 1:
                failed.append({
                    "id": audit["id"],
                    "title": audit.get("title"),
                    "description": audit.get("description", "")[:200],
                    "scoreDisplayMode": audit.get("scoreDisplayMode"),
                })
    return failed


def _correction_prompt(page: str, form_factor: str, failed: list[dict], scores: dict) -> str:
    lines = [
        f"Lighthouse {form_factor} audit for /{page} failed.",
        f"Scores: Performance={scores['performance']}, Accessibility={scores['accessibility']}, "
        f"BestPractices={scores['best_practices']}, SEO={scores['seo']}.",
        "Failed audits:",
    ]
    for a in failed[:10]:
        lines.append(f"- {a['id']}: {a['title']}")
    lines.append("Apply fixes and re-run the audit.")
    return "\n".join(lines)


def _audit_page(browser, port, base_url, page, out_dir, iteration):
    url = f"{base_url}/{page}"
    for i in range(1, MAX_ITERATIONS + 1):
        for form_factor in ("mobile", "desktop"):
            out_path = out_dir / f"{page}_{form_factor}_iter{i}.json"
            try:
                report = _run_lighthouse(port, url, out_path, form_factor)
            except RuntimeError as exc:
                return {"page": page, "status": "error", "error": str(exc)}
            scores = _scores(report)
            failed = _failed_audits(report)
            all_100 = all(v == 100 for v in scores.values())
            if all_100:
                return {"page": page, "status": "pass", "scores": scores, "iterations": i}

            # Last iteration: produce correction prompt and fail
            if i == MAX_ITERATIONS:
                prompt = _correction_prompt(page, form_factor, failed, scores)
                return {
                    "page": page,
                    "status": "fail",
                    "scores": scores,
                    "iterations": i,
                    "correction_prompt": prompt,
                }

            print(f"  /{page} {form_factor} iter {i}: {scores} — retrying")
    return {"page": page, "status": "fail", "error": "max iterations exceeded"}


def run(base_url: str, api_url: str, out_dir: Path, pages: list[str] | None = None) -> list[dict]:
    targets = pages or PAGES
    token = _get_token(api_url)
    playwright, browser, port = _launch_chrome()
    try:
        _set_auth_token(port, base_url, token)
        results = []
        for page in targets:
            print(f"Auditing /{page} ...")
            res = _audit_page(browser, port, base_url, page, out_dir, iteration=1)
            results.append(res)
            status = res.get("status")
            if status == "pass":
                print(f"  PASS /{page} ({res['iterations']} iterations)")
            elif status == "fail":
                print(f"  FAIL /{page}: {res.get('scores')}")
                print(f"  Correction prompt:\n{res.get('correction_prompt', '')}")
            else:
                print(f"  ERROR /{page}: {res.get('error')}")
        return results
    finally:
        browser.close()
        playwright.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Lighthouse hard-gate against BI app pages.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--out-dir", type=str, default=str(PROJECT_ROOT / "bi_platform" / ".tmp" / "lighthouse"))
    parser.add_argument("--pages", type=str, default=None, help="Comma-separated list of pages")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    pages = args.pages.split(",") if args.pages else None

    results = run(args.base_url, args.api_url, out_dir, pages)
    summary_path = PROJECT_ROOT / "bi_platform" / ".logs" / "lighthouse" / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    failed = [r for r in results if r.get("status") != "pass"]
    if failed:
        print(f"\n{len(failed)} page(s) failed the Lighthouse hard-gate.")
        return 1
    print("\nAll pages passed the Lighthouse hard-gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
