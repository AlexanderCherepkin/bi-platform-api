"""Generate TypeScript types and server actions from FastAPI OpenAPI schema.

Usage:
    python scripts/generators/openapi_to_typescript.py \
        --input scripts/openapi.json \
        --types-out vercel-app/src/lib/api/generated/types.ts \
        --actions-out vercel-app/src/lib/api/generated/actions.ts
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any


TS_KEYWORDS = {
    "break", "case", "catch", "class", "const", "continue", "debugger",
    "default", "delete", "do", "else", "enum", "export", "extends",
    "false", "finally", "for", "function", "if", "import", "in",
    "instanceof", "new", "null", "return", "super", "switch", "this",
    "throw", "true", "try", "typeof", "var", "void", "while", "with",
    "let", "static", "yield", "await", "of",
}


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if cleaned in TS_KEYWORDS or re.match(r"^[0-9]", cleaned):
        cleaned = "_" + cleaned
    return cleaned or "_"


def openapi_type_to_ts(schema: dict[str, Any], schemas: dict[str, Any]) -> str:
    if not isinstance(schema, dict):
        return "unknown"

    if "$ref" in schema:
        ref = schema["$ref"]
        name = ref.split("/")[-1]
        return name

    if "anyOf" in schema:
        parts = [openapi_type_to_ts(s, schemas) for s in schema["anyOf"]]
        # Collapse null unions
        non_null = [p for p in parts if p != "null"]
        if "null" in parts and len(non_null) == 1:
            return f"{non_null[0]} | null"
        return " | ".join(sorted(set(parts)))

    if "oneOf" in schema:
        parts = [openapi_type_to_ts(s, schemas) for s in schema["oneOf"]]
        non_null = [p for p in parts if p != "null"]
        if "null" in parts and len(non_null) == 1:
            return f"{non_null[0]} | null"
        return " | ".join(sorted(set(parts)))

    if "allOf" in schema:
        parts = [openapi_type_to_ts(s, schemas) for s in schema["allOf"]]
        return " & ".join(parts)

    t = schema.get("type")
    fmt = schema.get("format")

    if t is None and not schema:
        return "unknown"

    if t == "null":
        return "null"

    if t == "string":
        if fmt == "date":
            return "string /* date */"
        if fmt == "date-time":
            return "string /* date-time */"
        return "string"
    if t == "integer":
        return "number"
    if t == "number":
        return "number"
    if t == "boolean":
        return "boolean"
    if t == "array":
        item_ts = openapi_type_to_ts(schema.get("items", {}), schemas)
        return f"Array<{item_ts}>"
    if t == "object":
        additional = schema.get("additionalProperties")
        if additional:
            value_ts = openapi_type_to_ts(additional, schemas)
            return f"Record<string, {value_ts}>"
        props = schema.get("properties", {})
        if not props:
            return "Record<string, unknown>"
        lines = "{\n"
        for key, value in props.items():
            optional = "optional" if key not in schema.get("required", []) else ""
            field_type = openapi_type_to_ts(value, schemas)
            lines += f"    {safe_name(key)}{'?' if optional else ''}: {field_type};\n"
        lines += "  }"
        return lines

    return "unknown"


def generate_types(openapi: dict[str, Any]) -> str:
    schemas = openapi.get("components", {}).get("schemas", {})
    lines: list[str] = [
        "// Auto-generated from FastAPI OpenAPI schema",
        "// Do not edit manually — regenerate with scripts/generators/openapi_to_typescript.py",
        "",
    ]

    for name, schema in schemas.items():
        t = schema.get("type")
        if t == "object" and "properties" in schema:
            required = schema.get("required", [])
            lines.append(f"export interface {name} {{")
            for field, field_schema in schema["properties"].items():
                optional = field not in required
                field_type = openapi_type_to_ts(field_schema, schemas)
                # Inline object types are expanded; refs are named
                if field_type.startswith("{"):
                    field_type = field_type.replace("\n", "\n  ")
                lines.append(f"  {safe_name(field)}{'?' if optional else ''}: {field_type};")
            lines.append("}")
            lines.append("")
        else:
            ts = openapi_type_to_ts(schema, schemas)
            lines.append(f"export type {name} = {ts};")
            lines.append("")

    return "\n".join(lines) + "\n"


def path_to_action_name(method: str, path: str) -> str:
    parts = [p.strip("{}") for p in path.split("/") if p]
    method_part = method.lower()
    return "_".join([method_part] + parts)


def generate_actions(openapi: dict[str, Any]) -> str:
    lines: list[str] = [
        "'use server';",
        "",
        "// Auto-generated from FastAPI OpenAPI schema",
        "// Do not edit manually — regenerate with scripts/generators/openapi_to_typescript.py",
        "",
        "import { revalidatePath } from 'next/cache';",
        "import { apiFetch } from '@/lib/api';",
        "import type {",
    ]

    schemas = openapi.get("components", {}).get("schemas", {})
    for name in schemas:
        lines.append(f"  {name},")
    lines.append("} from './types';")
    lines.append("")

    operations: list[tuple[str, str, dict]] = []
    for path, methods in openapi.get("paths", {}).items():
        for method, op in methods.items():
            if method in ("get", "post", "put", "patch", "delete"):
                operations.append((method, path, op))

    for method, path, op in operations:
        action_name = safe_name(path_to_action_name(method, path))
        params: list[tuple[str, str]] = []
        path_params = re.findall(r"{([^}]+)}", path)
        for pp in path_params:
            params.append((safe_name(pp), "string | number"))

        body_schema: dict[str, Any] = {}
        content = op.get("requestBody", {}).get("content", {})
        if content:
            body_schema = content.get(
                "application/json",
                content.get("application/x-www-form-urlencoded", {}),
            ).get("schema", {})

        if "$ref" in body_schema:
            body_type = body_schema["$ref"].split("/")[-1]
            params.append(("payload", body_type))
        elif body_schema.get("type") == "object":
            params.append(("payload", openapi_type_to_ts(body_schema, schemas)))
        elif body_schema:
            params.append(("payload", openapi_type_to_ts(body_schema, schemas)))

        param_str = ", ".join(f"{n}: {t}" for n, t in params) if params else ""
        signature = f"export async function {action_name}({param_str}): Promise<any> {{"

        url = "`" + re.sub(r"{([^}]+)}", r"${\1}", path) + "`"
        method_upper = method.upper()

        has_json_body = method != "get" and any(n == "payload" for n, _ in params)
        json_content_type = False
        if content:
            json_content_type = "application/json" in content

        lines.append(signature)
        lines.append(f"  const res = await apiFetch({url}, {{")
        lines.append(f"    method: '{method_upper}',")
        if has_json_body:
            lines.append("    body: JSON.stringify(payload),")
        if has_json_body and json_content_type:
            lines.append("    headers: { 'Content-Type': 'application/json' },")
        lines.append("  });")
        lines.append("  revalidatePath('/');")
        lines.append("  return res;")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--types-out", required=True)
    parser.add_argument("--actions-out", required=True)
    args = parser.parse_args()

    openapi = json.loads(Path(args.input).read_text(encoding="utf-8"))

    types_ts = generate_types(openapi)
    Path(args.types_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.types_out).write_text(types_ts, encoding="utf-8")
    print(f"wrote {args.types_out}")

    actions_ts = generate_actions(openapi)
    Path(args.actions_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.actions_out).write_text(actions_ts, encoding="utf-8")
    print(f"wrote {args.actions_out}")


if __name__ == "__main__":
    main()
