#!/usr/bin/env python3
"""CLI wrapper that maps natural-language navigation intent to graphify commands.

Implements a tiny subset of the Agentic Loop tools_search/search_code pipeline
for this project by delegating to the existing graphify knowledge graph.
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GRAPH_JSON = PROJECT_ROOT / "graphify-out" / "graph.json"


def _run(cmd: list[str]) -> str:
    full = ["graphify", *cmd]
    try:
        result = subprocess.run(
            full,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "graphify CLI not found. Install with: pip install graphifyy"
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"graphify failed (exit {result.returncode}): {stderr}")

    return result.stdout.strip()


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\w\-]+", text.lower())


def _route_query(text: str) -> tuple[str, list[str]]:
    """Map natural-language intent to a graphify subcommand and arguments."""
    lowered = text.lower()
    tokens = _tokenize(text)

    # Path: "how is X related to Y", "связь между X и Y", "X → Y"
    path_markers = [
        " related to ",
        " connected to ",
        " links to ",
        "→",
        " связан",
        " связь ",
        " как ",
        " от ",
        " до ",
        " between ",
    ]
    if any(m in lowered for m in path_markers):
        parts = re.split(r"(?: related to | connected to | links to | → | связан с | связь между | как .* от | до | between | и )", lowered, flags=re.IGNORECASE)
        if len(parts) >= 2:
            a = parts[0].strip().strip("?")
            b = parts[-1].strip().strip("?")
            return "path", [a, b]

    # Explain: "what is X", "что такое X"
    explain_markers = ["what is ", "what are ", "explain ", "что такое ", "что делает "]
    for m in explain_markers:
        if lowered.startswith(m):
            concept = lowered[len(m):].strip().strip("?")
            return "explain", [concept]

    # Default: broad query
    return "query", [text]


def _keyword_route(text: str) -> str:
    """Narrow graphify query keywords based on domain vocabulary."""
    lowered = text.lower()
    domain_map = {
        "auth": ["login", "jwt", "token", "rbac", "role", "auth"],
        "dashboard": ["dashboard", "chart", "recharts", "pnl", "cashflow", "kpi"],
        "realtime": ["realtime", "websocket", "sse", "alerts", "alert-bell", "live-indicator"],
        "etl": ["etl", "1c", "amocrm", "google sheets", "counterparty"],
        "database": ["postgres", "prisma", "migration", "schema", "db-overview"],
        "ui": ["storybook", "component", "card", "table", "mobile-table", "switch"],
    }
    for keyword, markers in domain_map.items():
        if any(m in lowered for m in markers):
            return keyword
    return text


def do_query(text: str, dfs: bool = False, budget: int | None = None) -> str:
    keyword = _keyword_route(text)
    args = ["query", keyword]
    if dfs:
        args.append("--dfs")
    if budget:
        args.extend(["--budget", str(budget)])
    return _run(args)


def do_path(a: str, b: str) -> str:
    return _run(["path", a, b])


def do_explain(concept: str) -> str:
    return _run(["explain", concept])


def do_update() -> str:
    return _run([".", "--update"])


def dispatch(raw_text: str, dfs: bool = False, budget: int | None = None) -> str:
    subcommand, args = _route_query(raw_text)
    if subcommand == "path":
        return do_path(args[0], args[1])
    if subcommand == "explain":
        return do_explain(args[0])
    return do_query(raw_text, dfs=dfs, budget=budget)


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Agentic Loop graphify navigation wrapper for the BI project."
    )
    parser.add_argument("text", nargs="?", help="Natural-language navigation intent.")
    parser.add_argument(
        "--mode",
        choices=["auto", "query", "path", "explain", "update"],
        default="auto",
        help="Explicit subcommand; auto detects intent from text.",
    )
    parser.add_argument("--dfs", action="store_true", help="Use DFS for query mode.")
    parser.add_argument(
        "--budget", type=int, default=None, help="Token budget for query answers."
    )
    parser.add_argument(
        "--concept-a", type=str, default=None, help="First concept for path mode."
    )
    parser.add_argument(
        "--concept-b", type=str, default=None, help="Second concept for path mode."
    )
    args = parser.parse_args()

    if not GRAPH_JSON.exists():
        print(
            "graphify-out/graph.json not found. Run 'graphify .' from the project root first.",
            file=sys.stderr,
        )
        return 1

    try:
        if args.mode == "update":
            print(do_update())
            return 0

        if args.mode == "path":
            if not args.concept_a or not args.concept_b:
                print("--concept-a and --concept-b are required for path mode.", file=sys.stderr)
                return 2
            print(do_path(args.concept_a, args.concept_b))
            return 0

        if args.mode == "explain":
            if not args.text:
                print("text is required for explain mode.", file=sys.stderr)
                return 2
            print(do_explain(args.text))
            return 0

        if not args.text:
            parser.print_help()
            return 0

        print(dispatch(args.text, dfs=args.dfs, budget=args.budget))
        return 0
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
