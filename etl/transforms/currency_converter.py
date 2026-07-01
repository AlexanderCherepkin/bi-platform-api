from decimal import Decimal
from typing import Optional
import httpx


class CurrencyConverter:
    CBRF_URL = "https://www.cbr-xml-daily.ru/daily_json.js"

    def __init__(self, db_session=None):
        self.rates = {}
        self.db = db_session

    def fetch_cbrf_rates(self) -> dict:
        try:
            resp = httpx.get(self.CBRF_URL, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            rates = {"RUB": Decimal("1")}
            for code, info in data.get("Valute", {}).items():
                rates[code] = Decimal(str(info["Value"])) / Decimal(str(info["Nominal"]))
            self.rates = rates
            return rates
        except Exception:
            return {}

    def to_rub(self, amount: Decimal, currency_code: str, rate_value: Optional[Decimal] = None) -> Decimal:
        if currency_code == "RUB":
            return amount
        if rate_value is not None:
            return (amount * rate_value).quantize(Decimal("0.01"))
        if currency_code in self.rates:
            return (amount * self.rates[currency_code]).quantize(Decimal("0.01"))
        raise ValueError(f"No rate available for {currency_code}")

    def upsert_to_db(self, date_obj):
        if not self.db:
            return
        from sqlalchemy import text
        for code, rate in self.rates.items():
            if code == "RUB":
                continue
            self.db.execute(text("""
                INSERT INTO fact_exchange_rates (date_id, currency_from, currency_to, rate_value, source)
                VALUES (:d, :from, 'RUB', :rate, 'CBRF')
                ON CONFLICT (date_id, currency_from, currency_to, source)
                DO UPDATE SET rate_value = EXCLUDED.rate_value, created_at = NOW()
            """), {"d": date_obj, "from": code, "rate": float(rate)})
        self.db.commit()
