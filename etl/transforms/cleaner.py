import re
from datetime import datetime
from typing import Any, Optional
from decimal import Decimal, InvalidOperation


class DataCleaner:
    @staticmethod
    def parse_date(value: Any, fallback: Optional[datetime.date] = None) -> Optional[datetime.date]:
        if value is None:
            return fallback
        if isinstance(value, datetime.date):
            return value
        s = str(value).strip()
        # common Russian / mixed formats
        patterns = [
            "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y",
            "%m/%d/%Y", "%d-%m-%Y", "%Y.%m.%d",
            "%d.%m.%y", "%Y-%m-%d %H:%M:%S"
        ]
        for p in patterns:
            try:
                return datetime.strptime(s, p).date()
            except ValueError:
                continue
        return fallback

    @staticmethod
    def parse_decimal(value: Any, fallback: Optional[Decimal] = None) -> Optional[Decimal]:
        if value is None:
            return fallback
        if isinstance(value, Decimal):
            return value
        s = str(value).strip().replace(" ", "").replace("\xa0", "").replace("$", "").replace("€", "").replace("₽", "").replace(",", ".")
        try:
            return Decimal(s)
        except InvalidOperation:
            return fallback

    @staticmethod
    def parse_currency(raw: str, fallback: str = "RUB") -> str:
        if not raw:
            return fallback
        mapping = {
            "руб": "RUB", "rub": "RUB", "₽": "RUB", "р.": "RUB",
            "usd": "USD", "дол": "USD", "$": "USD",
            "cny": "CNY", "юан": "CNY", "¥": "CNY",
            "eur": "EUR", "евр": "EUR", "€": "EUR",
        }
        key = str(raw).strip().lower()
        return mapping.get(key, fallback.upper())

    @staticmethod
    def normalize_phone(phone: str) -> str:
        digits = re.sub(r"\D", "", str(phone))
        if digits.startswith("8") and len(digits) == 11:
            digits = "7" + digits[1:]
        if digits.startswith("7") and len(digits) == 11:
            return "+" + digits
        return digits

    @staticmethod
    def dedupe_candidates(records: list, key_func) -> list:
        seen = set()
        uniq = []
        for r in records:
            k = key_func(r)
            if k and k not in seen:
                seen.add(k)
                uniq.append(r)
        return uniq
