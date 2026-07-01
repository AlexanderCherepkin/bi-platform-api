"""
One-time remote DB bootstrap for Render/Fly/Railway.
Applies sorted SQL migrations once and seeds demo users and templates.
"""
import os
import glob
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from deps import engine
from init_db import main as seed_db

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db_migrations")


def ensure_migration_log_table(conn):
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    ))
    conn.commit()


def already_applied(conn, filename: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM schema_migrations WHERE filename = :fn"),
        {"fn": filename},
    )
    return result.scalar() is not None


def apply_migration(conn, filepath: str, filename: str):
    with open(filepath, "r", encoding="utf-8") as f:
        sql = f.read()
    if not sql.strip():
        return
    conn.execute(text(sql))
    conn.execute(
        text("INSERT INTO schema_migrations (filename, applied_at) VALUES (:fn, :at)"),
        {"fn": filename, "at": datetime.now(timezone.utc)},
    )
    conn.commit()
    print(f"Applied migration: {filename}")


def drop_all_tables(conn):
    print("DROP_ALL_TABLES=1: dropping all user tables across schemas...")
    result = conn.execute(text(
        """
        SELECT schemaname, tablename FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema');
        """
    ))
    rows = list(result)
    for schema, table in rows:
        conn.execute(text(f'DROP TABLE IF EXISTS "{schema}"."{table}" CASCADE;'))
    conn.commit()
    print(f"Dropped {len(rows)} tables.")


def main():
    print("Applying SQL migrations...")

    force_reinit = os.getenv("FORCE_REINIT", "0") == "1"
    drop_all = os.getenv("DROP_ALL_TABLES", "0") == "1"

    with engine.connect() as conn:
        if drop_all:
            drop_all_tables(conn)

        if force_reinit:
            print("FORCE_REINIT=1: resetting schema_migrations...")
            conn.execute(text("DROP TABLE IF EXISTS schema_migrations CASCADE;"))
            conn.commit()

        ensure_migration_log_table(conn)

        migration_files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
        for filepath in migration_files:
            filename = os.path.basename(filepath)
            if filename == "003_metabase_app_db.sql":
                print(f"Skipping Metabase-only migration: {filename}")
                continue
            if already_applied(conn, filename):
                print(f"Skipping already applied migration: {filename}")
                continue
            apply_migration(conn, filepath, filename)

    print("Seeding users and templates...")
    seed_db()
    print("Remote DB initialization complete.")


if __name__ == "__main__":
    main()
