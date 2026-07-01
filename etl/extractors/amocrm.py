import random
from datetime import date, timedelta
from typing import Any
import httpx
from etl.config import settings
from etl.extractors.base import Extractor


class AmoCRMExtractor(Extractor):
    source = "amoCRM"

    def __init__(self):
        self.demo_mode = settings.amocrm_demo_mode or not settings.amocrm_enabled
        self.base_url = settings.amocrm_base_url.rstrip("/")
        self.token = settings.amocrm_access_token

    def extract(self) -> dict[str, list[dict[str, Any]]]:
        if self.demo_mode:
            return {
                "leads": self._demo_leads(),
                "deals": self._demo_deals(),
            }
        return self._fetch_real()

    def _fetch_real(self) -> dict[str, list[dict[str, Any]]]:
        headers = {"Authorization": f"Bearer {self.token}"}
        leads_url = f"{self.base_url}/api/v4/leads"
        users_url = f"{self.base_url}/api/v4/users"
        with httpx.Client(headers=headers, timeout=60) as client:
            leads_resp = client.get(leads_url, params={"limit": 250})
            leads_resp.raise_for_status()
            users_resp = client.get(users_url, params={"limit": 250})
            users_resp.raise_for_status()
            leads_data = leads_resp.json().get("_embedded", {}).get("leads", [])
            users = {u["id"]: u["name"] for u in users_resp.json().get("_embedded", {}).get("users", [])}
        deals = []
        for lead in leads_data:
            if lead.get("price", 0) or lead.get("pipeline_id"):
                deals.append({
                    **lead,
                    "responsible_user_name": users.get(lead.get("responsible_user_id")),
                })
        return {"leads": leads_data, "deals": deals}

    def _demo_leads(self) -> list[dict[str, Any]]:
        today = date.today()
        statuses = ["new", "qualified", "converted", "lost"]
        channels = ["organic", "paid", "referral", "direct"]
        rows = []
        for i in range(40):
            d = today - timedelta(days=random.randint(0, 90))
            rows.append({
                "id": 1000 + i,
                "name": f"Лид демо {i+1}",
                "status_id": random.choice([142, 143, 144]),
                "pipeline_id": 100,
                "responsible_user_id": random.choice([1, 2, 3]),
                "created_at": int(d.strftime("%s")),
                "updated_at": int(d.strftime("%s")),
                "price": 0,
                "_embedded": {"contacts": [{"id": 5000 + i}]},
                "source_channel": random.choice(channels),
                "lead_status": random.choice(statuses),
                "utm_source": random.choice(["yandex", "google", ""]),
                "utm_medium": random.choice(["cpc", "organic", ""]),
            })
        return rows

    def _demo_deals(self) -> list[dict[str, Any]]:
        today = date.today()
        rows = []
        for i in range(30):
            d = today - timedelta(days=random.randint(0, 120))
            close_d = d + timedelta(days=random.randint(5, 60)) if random.random() > 0.3 else None
            amount = round(random.uniform(10000, 200000), 2)
            status = random.choice(["open", "won", "lost"])
            rows.append({
                "id": 2000 + i,
                "name": f"Сделка демо {i+1}",
                "status_id": random.choice([142, 143, 144, 145]),
                "pipeline_id": 100,
                "responsible_user_id": random.choice([1, 2, 3]),
                "created_at": int(d.strftime("%s")),
                "closed_at": int(close_d.strftime("%s")) if close_d else None,
                "price": amount,
                "currency": "RUB",
                "pipeline_name": "Основная воронка",
                "stage_name": random.choice(["Первичный контакт", "Презентация", "Коммерческое", "Закрыто"]),
                "deal_status": status,
                "probability_pct": 100 if status == "won" else (0 if status == "lost" else random.randint(20, 80)),
            })
        return rows
