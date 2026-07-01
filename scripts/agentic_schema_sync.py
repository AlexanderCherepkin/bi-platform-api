#!/usr/bin/env python3
"""Backend Spec Bridge — SQL migrations → TypeScript interfaces + Next.js Server Actions.

Implements a simplified backend_spec_bridge pipeline for the BI project:
parse SQL migrations, infer TypeScript types, and generate reusable frontend
contracts plus Server Actions that call the FastAPI /api/db/query endpoint.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "bi_platform" / "scripts" / "schema_sync.config.json"


@dataclass
class Column:
    name: str
    pg_type: str
    nullable: bool = True
    default: str | None = None
    is_pk: bool = False
    is_fk: bool = False
    fk_ref: str | None = None


@dataclass
class Table:
    name: str
    kind: str = "table"  # table | view
    columns: list[Column] = field(default_factory=list)


def _pg_type_to_ts(pg_type: str) -> str:
    lowered = pg_type.lower()
    if any(t in lowered for t in ("serial", "integer", "int", "bigint", "smallint")):
        return "number"
    if any(t in lowered for t in ("numeric", "decimal", "real", "double", "float")):
        return "number"
    if any(t in lowered for t in ("varchar", "char", "text", "uuid")):
        return "string"
    if any(t in lowered for t in ("boolean", "bool")):
        return "boolean"
    if any(t in lowered for t in ("date", "timestamp", "time")):
        return "string"
    if any(t in lowered for t in ("json", "jsonb")):
        return "Record<string, any>"
    return "any"


def _ts_type(col: Column) -> str:
    base = _pg_type_to_ts(col.pg_type)
    if col.nullable:
        return f"{base} | null"
    return base


def _to_camel(snake: str) -> str:
    parts = snake.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _to_pascal(snake: str) -> str:
    return "".join(p.capitalize() for p in snake.split("_"))


def _parse_column(line: str) -> Column | None:
    line = line.strip()
    if not line or line.startswith("--"):
        return None
    upper = line.upper()
    if any(upper.startswith(k) for k in ("CONSTRAINT", "PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "INDEX", "CREATE", ")")):
        return None
    if "UNIQUE" in upper and "(" in line and not any(t in upper for t in ("VARCHAR", "CHAR", "TEXT", "INT", "SERIAL", "NUMERIC", "DECIMAL", "BOOL", "DATE", "TIMESTAMP", "JSON")):
        return None

    # strip inline comment
    line = re.sub(r"\s*--.*$", "", line)
    if not line:
        return None

    # Match: column_name TYPE [constraints]
    m = re.match(
        r'^\s*"?(?P<name>[\w_]+)"?\s+(?P<type>[\w\s\(\),\.\[\]]+?)(?:\s+(?P<rest>[^,]*?))?\s*,?\s*$',
        line,
        re.IGNORECASE,
    )
    if not m:
        return None

    name = m.group("name").strip()
    pg_type = m.group("type").strip()
    rest = (m.group("rest") or "").upper()

    nullable = "NOT NULL" not in rest
    default_m = re.search(r"DEFAULT\s+(.+?)(?:\s+(?:NOT\s+NULL|NULL|UNIQUE|PRIMARY|REFERENCES|CHECK|$))", rest, re.IGNORECASE)
    default = default_m.group(1).strip() if default_m else None
    is_pk = "PRIMARY KEY" in rest
    fk_m = re.search(r"REFERENCES\s+(\w+)\s*\(\s*(\w+)\s*\)", rest, re.IGNORECASE)
    fk_ref = f"{fk_m.group(1)}.{fk_m.group(2)}" if fk_m else None

    return Column(
        name=name,
        pg_type=pg_type,
        nullable=nullable,
        default=default,
        is_pk=is_pk,
        is_fk=fk_ref is not None,
        fk_ref=fk_ref,
    )


def _extract_block(sql: str, keyword: str, name_pattern: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        rf"{keyword}\s+(?:(?:IF\s+NOT\s+EXISTS)\s+)?(?P<name>{name_pattern})\s*\((?P<body>[^;]+?)\);",
        re.IGNORECASE | re.DOTALL,
    )
    return [(m.group("name"), m.group("body")) for m in pattern.finditer(sql)]


def parse_migrations(migrations_dir: Path) -> list[Table]:
    all_sql = ""
    for path in sorted(migrations_dir.glob("*.sql")):
        all_sql += f"\n-- file: {path.name}\n" + path.read_text(encoding="utf-8")

    tables: list[Table] = []

    # Regular CREATE TABLE
    for name, body in _extract_block(all_sql, r"CREATE\s+TABLE", r'(?:public\.)?"?(\w+)"?'):
        cols: list[Column] = []
        for raw_line in body.splitlines():
            col = _parse_column(raw_line)
            if col:
                cols.append(col)
        tables.append(Table(name=name, kind="table", columns=cols))

    # CREATE VIEW (materialized and regular)
    for m in re.finditer(
        r"CREATE\s+(?:MATERIALIZED\s+)?VIEW\s+(?:(?:IF\s+NOT\s+EXISTS)\s+)?(?:public\.)?[\"]?(\w+)[\"]?\s+AS\s+(.+?);",
        all_sql,
        re.IGNORECASE | re.DOTALL,
    ):
        name = m.group(1)
        tables.append(Table(name=name, kind="view", columns=[]))

    return tables


def generate_types(tables: list[Table], config: dict[str, Any]) -> str:
    lines = [
        "// Auto-generated from SQL migrations by agentic_schema_sync.py",
        "// Do not edit manually; re-run schema sync.",
        "",
    ]

    whitelist = config.get("whitelist", [])
    blacklist = config.get("blacklist", [])

    for table in tables:
        if whitelist and table.name not in whitelist:
            continue
        if table.name in blacklist:
            continue
        if table.kind == "view":
            lines.append(f"// View: {table.name}")
            lines.append(f"export interface {_to_pascal(table.name)}Row {{}}")
            lines.append("")
            continue

        iface = _to_pascal(table.name)
        lines.append(f"export interface {iface} {{")
        for col in table.columns:
            optional = "?" if col.nullable or col.default is not None else ""
            lines.append(f"  {col.name}{optional}: {_ts_type(col)};")
        lines.append("}")
        lines.append(f"export type {iface}Insert = Omit<{iface}, {_pk_field_names(table)}>;")
        lines.append("")

    return "\n".join(lines)


def _pk_field_names(table: Table) -> str:
    pks = [c.name for c in table.columns if c.is_pk]
    if len(pks) == 1:
        return f'"{pks[0]}"'
    return "never"


def _api_base_url_expr(config: dict[str, Any]) -> str:
    env = config.get("api_base_url_env", "NEXT_PUBLIC_API_URL")
    default = config.get("default_api_base_url", "http://localhost:8000")
    return f'process.env.{env} || "{default}"'


def generate_actions(tables: list[Table], config: dict[str, Any]) -> str:
    base_url = _api_base_url_expr(config)
    allowed = set(config.get("server_actions_for", []))
    blacklist = set(config.get("blacklist", []))

    lines = [
        "'use server';",
        "",
        "// Auto-generated from SQL migrations by agentic_schema_sync.py",
        "// Do not edit manually; re-run schema sync.",
        "",
        'import { revalidatePath } from "next/cache";',
        f'import * as Types from "@/types/generated/schema";',
        "",
        "async function queryDb(sql: string, params?: Record<string, any>) {",
        f"  const baseUrl = {base_url};",
        '  const res = await fetch(`${baseUrl}/api/db/query`, {',
        '    method: "POST",',
        '    headers: { "Content-Type": "application/json" },',
        '    body: JSON.stringify({ sql, params }),',
        '  });',
        "  if (!res.ok) {",
        "    const err = await res.text();",
        "    throw new Error(`DB query failed: ${err}`);",
        "  }",
        "  return res.json();",
        "}",
        "",
    ]

    for table in tables:
        if table.kind == "view":
            continue
        if table.name in blacklist:
            continue
        if allowed and table.name not in allowed:
            continue

        pk_cols = [c for c in table.columns if c.is_pk]
        if not pk_cols:
            continue
        pk = pk_cols[0]
        iface = _to_pascal(table.name)
        insert = f"{iface}Insert"
        fields = ", ".join(c.name for c in table.columns if not c.is_pk)
        placeholders = ", ".join(f":{c.name}" for c in table.columns if not c.is_pk)
        update_pairs = ", ".join(f"{c.name} = :{c.name}" for c in table.columns if not c.is_pk)

        lines.append(f"// Actions for {table.name}")
        lines.append(f"export async function list{_to_pascal(table.name)}(): Promise<Types.{iface}[]> {{")
        lines.append(f'  const data = await queryDb("SELECT * FROM {table.name} LIMIT 1000");')
        lines.append("  return data.rows;")
        lines.append("}")
        lines.append("")

        lines.append(f"export async function get{_to_pascal(table.name)}ById(id: number): Promise<Types.{iface} | null> {{")
        lines.append(f'  const data = await queryDb("SELECT * FROM {table.name} WHERE {pk.name} = :id", {{ id }});')
        lines.append("  return data.rows[0] ?? null;")
        lines.append("}")
        lines.append("")

        lines.append(f"export async function create{_to_pascal(table.name)}(input: Types.{insert}): Promise<Types.{iface}> {{")
        lines.append(f'  const data = await queryDb("INSERT INTO {table.name} ({fields}) VALUES ({placeholders}) RETURNING *", input as any);')
        lines.append("  revalidatePath('/');")
        lines.append("  return data.rows[0];")
        lines.append("}")
        lines.append("")

        lines.append(f"export async function update{_to_pascal(table.name)}(id: number, input: Partial<Types.{insert}>): Promise<Types.{iface}> {{")
        lines.append(f'  const data = await queryDb("UPDATE {table.name} SET {update_pairs} WHERE {pk.name} = :id RETURNING *", {{ ...input, id }});')
        lines.append("  revalidatePath('/');")
        lines.append("  return data.rows[0];")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def write_outputs(tables: list[Table], config: dict[str, Any], dry_run: bool) -> None:
    types_dir = PROJECT_ROOT / config["output_dir_types"]
    actions_dir = PROJECT_ROOT / config["output_dir_actions"]

    if not dry_run:
        types_dir.mkdir(parents=True, exist_ok=True)
        actions_dir.mkdir(parents=True, exist_ok=True)

    types_content = generate_types(tables, config)
    actions_content = generate_actions(tables, config)

    types_path = types_dir / "schema.ts"
    actions_path = actions_dir / "index.ts"

    if dry_run:
        print(f"[dry-run] Would write {types_path}")
        print(types_content[:1000] + ("\n..." if len(types_content) > 1000 else ""))
        print(f"\n[dry-run] Would write {actions_path}")
        print(actions_content[:1000] + ("\n..." if len(actions_content) > 1000 else ""))
        return

    types_path.write_text(types_content, encoding="utf-8")
    actions_path.write_text(actions_content, encoding="utf-8")
    print(f"Wrote {types_path}")
    print(f"Wrote {actions_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync SQL migrations to TypeScript + Server Actions.")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    migrations_dir = PROJECT_ROOT / config["migrations_dir"]
    tables = parse_migrations(migrations_dir)
    print(f"Parsed {len(tables)} tables/views from {migrations_dir}")

    write_outputs(tables, config, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
