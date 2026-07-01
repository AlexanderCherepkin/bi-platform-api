import random
from datetime import date, timedelta
from typing import Any
import httpx
from etl.config import settings
from etl.extractors.base import Extractor


class OneCExtractor(Extractor):
    source = "1C"

    def __init__(self):
        self.demo_mode = settings.onec_demo_mode or not settings.onec_enabled
        self.base_url = settings.onec_base_url
        self.username = settings.onec_username
        self.password = settings.onec_password

    def extract(self) -> list[dict[str, Any]]:
        if self.demo_mode:
            return self._demo_data()
        return self._fetch_real()

    def _fetch_real(self) -> list[dict[str, Any]]:
        auth = (self.username, self.password) if self.username and self.password else None
        response = httpx.get(
            f"{self.base_url}/transactions",
            auth=auth,
            timeout=60,
        )
        response.raise_for_status()
        return response.json().get("transactions", [])

    def _demo_data(self) -> list[dict[str, Any]]:
        today = date.today()
        rows = []
        account_pairs = [
            ("62.01", "90.01.1", "revenue"),
            ("90.02.1", "41.01", "cogs"),
            ("26", "60.01", "opex"),
            ("68.04.2", "99.01", "tax"),
        ]
        for i in range(30):
            d = today - timedelta(days=i * 3)
            debit, credit, kind = random.choice(account_pairs)
            amount = round(random.uniform(1000, 50000), 2)
            rows.append({
                "doc_number": f"1C-DEMO-{i+1:04d}",
                "doc_date": d.isoformat(),
                "doc_type": random.choice(["Реализация", "Поступление", "Списание"]),
                "organization": "ООО Демо",
                "counterparty_name": random.choice(["ООО Клиент А", "ИП Поставщик Б", "ООО Партнер В"]),
                "counterparty_inn": f"{random.randint(1000000000, 9999999999):010d}",
                "account_debit": debit,
                "account_credit": credit,
                "amount": amount,
                "currency_code": "RUB",
                "description": f"Демо проводка {kind}",
            })
        return rows
