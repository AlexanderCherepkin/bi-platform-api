"""
One-time remote DB bootstrap for Render/Fly/Railway.
Creates tables from SQLAlchemy models, applies sorted SQL migrations once,
and seeds demo users and templates.
"""
import os
import glob
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from deps import engine
from models import Base
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


def main():
    print("Creating SQLAlchemy tables if missing...")
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        ensure_migration_log_table(conn)

        migration_files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
        for filepath in migration_files:
            filename = os.path.basename(filepath)
            if already_applied(conn, filename):
                print(f"Skipping already applied migration: {filename}")
                continue
            apply_migration(conn, filepath, filename)

    print("Seeding users and templates...")
    seed_db()
    print("Remote DB initialization complete.")


if __name__ == "__main__":
    main()
