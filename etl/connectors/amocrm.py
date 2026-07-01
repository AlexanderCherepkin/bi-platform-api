import os
import time
from typing import List, Dict, Any
import httpx
from .base import Connector


class AmoCrmConnector(Connector):
    def __init__(self, subdomain: str = None, client_id: str = None, client_secret: str = None, redirect_uri: str = None):
        self.subdomain = subdomain or os.getenv("AMOCRM_SUBDOMAIN")
        self.client_id = client_id or os.getenv("AMOCRM_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("AMOCRM_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv("AMOCRM_REDIRECT_URI")
        self.access_token = os.getenv("AMOCRM_ACCESS_TOKEN")
        self.refresh_token = os.getenv("AMOCRM_REFRESH_TOKEN")
        self.base_url = f"https://{self.subdomain}.amocrm.ru/api/v4"

    def authenticate(self) -> bool:
        if self.access_token:
            return True
        # Refresh flow stub — real implementation would handle OAuth2 token refresh
        return False

    def fetch(self, entity: str = "leads", limit: int = 200, **filters) -> List[Dict[str, Any]]:
        """Fetch leads or contacts from amoCRM. Pagination handled automatically."""
        if not self.authenticate():
            raise RuntimeError("amoCRM not authenticated")

        results = []
        page = 1
        while True:
            params = {"limit": limit, "page": page, "with": "contacts"}
            params.update(filters)
            resp = httpx.get(
                f"{self.base_url}/{entity}",
                headers={"Authorization": f"Bearer {self.access_token}"},
                params=params,
                timeout=30.0
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("_embedded", {}).get(entity, [])
            if not items:
                break
            results.extend(items)
            if len(items) < limit:
                break
            page += 1
            time.sleep(0.2)  # rate-limit kindness
        return results

    def fetch_leads(self, updated_after: str = None) -> List[Dict[str, Any]]:
        filters = {}
        if updated_after:
            filters["updated_since"] = updated_after
        return self.fetch(entity="leads", **filters)

    def fetch_contacts(self, updated_after: str = None) -> List[Dict[str, Any]]:
        filters = {}
        if updated_after:
            filters["updated_since"] = updated_after
        return self.fetch(entity="contacts", **filters)
