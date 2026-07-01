#!/usr/bin/env python3
"""Master quality gate orchestrator for the BI app.

Runs the Agentic Loop integration pipeline end-to-end:
1. schema sync (SQL → TypeScript + Server Actions)
2. Next.js build
3. start production server
4. screenshot regression
5. Lighthouse hard-gate
6. shutdown production server
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERCEL_APP = PROJECT_ROOT / "bi_platform" / "vercel-app"
SCRIPTS = PROJECT_ROOT / "bi_platform" / "scripts"
DEFAULT_BASE_URL = "http://localhost:3000"
DEFAULT_API_URL = "http://localhost:8000"


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int | None = None) -> int:
    print(f"\n$ {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
        print(f"TIMEOUT after {timeout}s\n{out}", file=sys.stderr)
        return 1
    print(out[-4000:] if len(out) > 4000 else out)
    return proc.returncode


def _start_server(base_url: str) -> subprocess.Popen:
    print("\nStarting Next.js production server...")
    env = {**os.environ, "PORT": "3000"}
    proc = subprocess.Popen(
        ["npm", "start"],
        cwd=VERCEL_APP,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Wait for server readiness
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            import urllib.request
            urllib.request.urlopen(base_url, timeout=2)
            print("Server ready.")
            return proc
        except Exception:
            time.sleep(1)
    proc.kill()
    raise RuntimeError(f"Server did not become ready at {base_url}")


def _stop_server(proc: subprocess.Popen) -> None:
    print("\nStopping Next.js production server...")
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full Agentic Loop quality gate for BI app.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--skip-schema-sync", action="store_true")
    parser.add_argument("--skip-screenshots", action="store_true")
    parser.add_argument("--skip-lighthouse", action="store_true")
    args = parser.parse_args()

    report: dict = {"steps": []}
    server_proc = None
    overall = 0

    try:
        if not args.skip_schema_sync:
            rc = _run(["python", str(SCRIPTS / "agentic_schema_sync.py")], PROJECT_ROOT, timeout=120)
            report["steps"].append({"name": "schema_sync", "ok": rc == 0})
            if rc != 0:
                overall = 1

        rc = _run(["npm", "run", "build"], VERCEL_APP, timeout=300)
        report["steps"].append({"name": "next_build", "ok": rc == 0})
        if rc != 0:
            overall = 1

        if overall == 0:
            server_proc = _start_server(args.base_url)

            if not args.skip_screenshots:
                rc = _run(
                    ["python", str(SCRIPTS / "agentic_screenshots.py"), "--base-url", args.base_url, "--api-url", args.api_url],
                    PROJECT_ROOT,
                    timeout=300,
                )
                report["steps"].append({"name": "screenshots", "ok": rc == 0})
                if rc != 0:
                    overall = 1

            if not args.skip_lighthouse:
                rc = _run(
                    ["python", str(SCRIPTS / "agentic_lighthouse.py"), "--base-url", args.base_url, "--api-url", args.api_url],
                    PROJECT_ROOT,
                    timeout=600,
                )
                report["steps"].append({"name": "lighthouse", "ok": rc == 0})
                if rc != 0:
                    overall = 1

        report["overall_ok"] = overall == 0
        log_dir = PROJECT_ROOT / "bi_platform" / ".logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "agentic_quality_gate.json"
        log_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nReport written to {log_path}")

        if overall == 0:
            print("\n✅ Agentic Loop quality gate passed.")
        else:
            print("\n❌ Agentic Loop quality gate failed — see report.")
        return overall
    finally:
        if server_proc:
            _stop_server(server_proc)


if __name__ == "__main__":
    raise SystemExit(main())
