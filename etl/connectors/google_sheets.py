import os
from typing import List, Dict, Any
import httpx
from .base import Connector


class GoogleSheetsConnector(Connector):
    def __init__(self, credentials_json: str = None, spreadsheet_ids: str = None):
        self.credentials_json = credentials_json or os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
        self.spreadsheet_ids = (spreadsheet_ids or os.getenv("GOOGLE_SHEETS_SPREADSHEET_IDS", "")).split(",")
        self.access_token = None

    def authenticate(self) -> bool:
        # In real setup: read service-account JSON, generate JWT, exchange for access token
        # Stub: assume token injected via env or pre-fetched
        self.access_token = os.getenv("GOOGLE_ACCESS_TOKEN")
        return bool(self.access_token)

    def fetch(self, spreadsheet_id: str = None, range_name: str = None, **kwargs) -> List[Dict[str, Any]]:
        if not self.authenticate():
            raise RuntimeError("Google Sheets not authenticated")
        sid = spreadsheet_id or self.spreadsheet_ids[0]
        rng = range_name or "Sheet1"
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/{rng}"
        resp = httpx.get(url, headers={"Authorization": f"Bearer {self.access_token}"}, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        values = data.get("values", [])
        if not values:
            return []
        headers = [h.strip().lower().replace(" ", "_") for h in values[0]]
        rows = []
        for i, row in enumerate(values[1:], start=2):
            # pad short rows with None
            padded = row + [None] * (len(headers) - len(row))
            record = dict(zip(headers, padded))
            record["_row_num"] = i
            record["_sheet_name"] = rng
            rows.append(record)
        return rows

    def fetch_all_tabs(self, spreadsheet_id: str = None) -> Dict[str, List[Dict[str, Any]]]:
        sid = spreadsheet_id or self.spreadsheet_ids[0]
        # Discover tabs
        meta_url = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}?fields=sheets.properties.title"
        resp = httpx.get(meta_url, headers={"Authorization": f"Bearer {self.access_token}"}, timeout=30.0)
        resp.raise_for_status()
        sheets = resp.json().get("sheets", [])
        results = {}
        for s in sheets:
            title = s["properties"]["title"]
            results[title] = self.fetch(spreadsheet_id=sid, range_name=title)
        return results
