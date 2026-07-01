import csv
import io
import random
from datetime import date, timedelta
from typing import Any
import httpx
from etl.config import settings
from etl.extractors.base import Extractor


class GoogleSheetsExtractor(Extractor):
    source = "GoogleSheets"

    def __init__(self):
        self.demo_mode = settings.gsheets_demo_mode or not settings.gsheets_enabled
        self.sheet_id = settings.gsheets_sheet_id
        self.gid = settings.gsheets_gid

    def extract(self) -> list[dict[str, Any]]:
        if self.demo_mode:
            return self._demo_data()
        return self._fetch_csv()

    def _fetch_csv(self) -> list[dict[str, Any]]:
        if not self.sheet_id:
            return []
        url = (
            "https://docs.google.com/spreadsheets/d/"
            f"{self.sheet_id}/export?format=csv&id={self.sheet_id}&gid={self.gid}"
        )
        resp = httpx.get(url, timeout=60)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text, newline=""))
        return list(reader)

    def _demo_data(self) -> list[dict[str, Any]]:
        today = date.today()
        categories = [
            ("Канцелярия", "Бумага A4", "OPEX-005"),
            ("Маркетинг", "Яндекс Директ", "OPEX-003"),
            ("Аренда", "Аренда офиса", "OPEX-002"),
            ("Логистика", "Доставка СДЭК", "OPEX-006"),
            ("Связь", "МТС", "OPEX-007"),
        ]
        rows = []
        for i in range(25):
            d = today - timedelta(days=random.randint(0, 60))
            category, item, account = random.choice(categories)
            rows.append({
                "date_raw": d.strftime("%d.%m.%Y"),
                "amount_raw": str(round(random.uniform(500, 15000), 2)).replace(".", ","),
                "currency_raw": "RUB",
                "category_raw": category,
                "item_raw": item,
                "department_raw": random.choice(["SALES", "MARKETING", "IT"]),
                "description_raw": f"Демо расход {i+1}",
            })
        return rows
