import os
from typing import List, Dict, Any
import httpx
from .base import Connector


class OneCConnector(Connector):
    def __init__(self, base_url: str = None, username: str = None, password: str = None):
        self.base_url = (base_url or os.getenv("ONEC_BASE_URL", "")).rstrip("/")
        self.username = username or os.getenv("ONEC_USERNAME")
        self.password = password or os.getenv("ONEC_PASSWORD")
        self.session = httpx.Client(auth=(self.username, self.password), timeout=60.0)

    def authenticate(self) -> bool:
        # 1C OData/Webhook auth is Basic HTTP; session holds creds
        return bool(self.username and self.password)

    def fetch(self, entity_set: str = "Catalog_Контрагенты", top: int = 500, skip: int = 0, **filters) -> List[Dict[str, Any]]:
        if not self.authenticate():
            raise RuntimeError("1C credentials not configured")
        # OData v4 query
        url = f"{self.base_url}/odata/standard.odata/{entity_set}"
        params = {"$top": top, "$skip": skip, "$format": "json"}
        if filters:
            filter_parts = []
            for k, v in filters.items():
                filter_parts.append(f"{k} eq '{v}'")
            params["$filter"] = " and ".join(filter_parts)
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("value", [])

    def fetch_documents(self, doc_type: str = "Document_РеализацияТоваровУслуг", date_from: str = None, date_to: str = None) -> List[Dict[str, Any]]:
        filters = {}
        if date_from:
            filters["Date"] = f"'{date_from}'"
        return self.fetch(entity_set=f"{doc_type}", **filters)

    def fetch_registers(self, register_type: str = "AccumulationRegister_Продажи", period_from: str = None, period_to: str = None) -> List[Dict[str, Any]]:
        filters = {}
        if period_from:
            filters["Period"] = f"'{period_from}'"
        return self.fetch(entity_set=f"{register_type}", **filters)
