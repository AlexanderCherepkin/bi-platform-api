#!/usr/bin/env python3
"""
Bootstrap Metabase after first start:
1. Wait for Metabase readiness
2. Create admin user
3. Add PostgreSQL database connection
4. (Optional) Create collections/questions via API

Requires: METABASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD env vars.
"""
import os
import sys
import time
import httpx

METABASE_URL = os.getenv("METABASE_URL", "http://localhost:3001")
ADMIN_EMAIL = os.getenv("METABASE_ADMIN_EMAIL", "admin@company.local")
ADMIN_PASSWORD = os.getenv("METABASE_ADMIN_PASSWORD", "CorpB1_Pass2024!")
DB_HOST = os.getenv("MB_DB_HOST", "db")
DB_PORT = int(os.getenv("MB_DB_PORT", "5432"))
DB_NAME = os.getenv("MB_DB_DBNAME", "bi_dwh")
DB_USER = os.getenv("MB_DB_USER", "bi_admin")
DB_PASS = os.getenv("MB_DB_PASS", "bi_secret")


def wait_for_ready(timeout: int = 120):
    print("Waiting for Metabase to be ready...")
    for _ in range(timeout):
        try:
            r = httpx.get(f"{METABASE_URL}/api/health", timeout=5.0)
            if r.status_code == 200 and r.json().get("status") == "ok":
                print("Metabase is ready.")
                return True
        except Exception:
            pass
        time.sleep(1)
    print("Timeout waiting for Metabase.")
    return False


def get_setup_token():
    r = httpx.get(f"{METABASE_URL}/api/session/properties", timeout=10.0)
    r.raise_for_status()
    return r.json().get("setup-token")


def setup_admin():
    print("Setting up admin user...")
    token = get_setup_token()
    if not token:
        print("No setup token available (already initialized?).")
        return None
    payload = {
        "token": token,
        "user": {
            "first_name": "Admin",
            "last_name": "User",
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        },
        "prefs": {"site_name": "Corp BI", "site_locale": "ru"}
    }
    r = httpx.post(f"{METABASE_URL}/api/setup", json=payload, timeout=30.0)
    if r.status_code in (200, 201):
        print("Admin created.")
        return r.json()
    if r.status_code == 400 and "already exists" in r.text.lower():
        print("Admin already exists.")
        return None
    print(f"Setup error: {r.status_code} {r.text}")
    return None


def get_session_token():
    r = httpx.post(f"{METABASE_URL}/api/session", json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30.0)
    r.raise_for_status()
    return r.json()["id"]


def add_database(session_id: str):
    print("Adding DWH database connection...")
    headers = {"X-Metabase-Session": session_id}
    payload = {
        "name": "BI DWH",
        "engine": "postgres",
        "details": {
            "host": DB_HOST,
            "port": DB_PORT,
            "dbname": DB_NAME,
            "user": DB_USER,
            "password": DB_PASS,
            "ssl": False,
            "tunnel-enabled": False,
            "advanced-options": False
        },
        "is_full_sync": True,
        "is_on_demand": False
    }
    r = httpx.post(f"{METABASE_URL}/api/database", headers=headers, json=payload, timeout=30.0)
    if r.status_code in (200, 201):
        print("Database connected.")
        return r.json()
    if r.status_code == 400 and "already exists" in r.text.lower():
        print("Database already exists.")
        return None
    print(f"Database add error: {r.status_code} {r.text}")
    return None


def main():
    if not wait_for_ready():
        sys.exit(1)
    setup_admin()
    token = get_session_token()
    add_database(token)
    print("Metabase bootstrap complete.")


if __name__ == "__main__":
    main()
