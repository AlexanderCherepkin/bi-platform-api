"""
Initialize BI DWH with seed users and data input templates.
Run once after first deploy or after `docker compose up -d db`.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext
from models import BiUser, DataInputTemplate

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://bi_admin:bi_secret@localhost:5432/bi_dwh")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def init_users(db):
    users = [
        {"username": "admin", "email": "admin@company.local", "password": "admin123", "role": "admin", "full_name": "Администратор BI"},
        {"username": "ceo", "email": "ceo@company.local", "password": "ceo123", "role": "ceo", "full_name": "Генеральный директор"},
        {"username": "cfo", "email": "cfo@company.local", "password": "cfo123", "role": "cfo", "full_name": "Финансовый директор"},
        {"username": "sales_head", "email": "sales@company.local", "password": "sales123", "role": "sales_head", "full_name": "Руководитель продаж"},
        {"username": "manager1", "email": "m1@company.local", "password": "manager123", "role": "manager", "full_name": "Менеджер по продажам"},
    ]
    for u in users:
        exists = db.query(BiUser).filter(BiUser.username == u["username"]).first()
        if not exists:
            db.add(BiUser(
                username=u["username"],
                email=u["email"],
                hashed_password=pwd_ctx.hash(u["password"]),
                full_name=u["full_name"],
                role=u["role"]
            ))
    db.commit()
    print("Users seeded.")


def init_templates(db):
    templates = [
        {
            "template_code": "expense_quick",
            "template_name": "Быстрый расход",
            "target_table": "fact_expenses",
            "allowed_roles": ["admin", "cfo", "manager"],
            "json_schema": {
                "type": "object",
                "properties": {
                    "expense_date": {"type": "string", "format": "date", "title": "Дата расхода"},
                    "expense_category": {"type": "string", "title": "Категория"},
                    "expense_item": {"type": "string", "title": "Статья"},
                    "amount": {"type": "number", "minimum": 0.01, "title": "Сумма"},
                    "currency": {"type": "string", "enum": ["RUB", "USD", "CNY"], "title": "Валюта"},
                    "description": {"type": "string", "title": "Описание"}
                },
                "required": ["expense_date", "expense_category", "expense_item", "amount", "currency"]
            }
        },
        {
            "template_code": "sales_plan",
            "template_name": "План продаж на месяц",
            "target_table": "data_plans",  # placeholder until plans table is built
            "allowed_roles": ["admin", "sales_head", "manager"],
            "json_schema": {
                "type": "object",
                "properties": {
                    "month": {"type": "string", "format": "date", "title": "Месяц"},
                    "target_revenue": {"type": "number", "minimum": 0, "title": "Целевая выручка (RUB)"},
                    "target_deals": {"type": "integer", "minimum": 0, "title": "Целевое количество сделок"}
                },
                "required": ["month", "target_revenue"]
            }
        },
        {
            "template_code": "currency_rate_manual",
            "template_name": "Курс валюты (ручной)",
            "target_table": "fact_exchange_rates",
            "allowed_roles": ["admin", "cfo"],
            "json_schema": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "format": "date", "title": "Дата"},
                    "currency_from": {"type": "string", "enum": ["USD", "CNY", "EUR"], "title": "Валюта"},
                    "rate_value": {"type": "number", "minimum": 0.0001, "title": "Курс к RUB"}
                },
                "required": ["date", "currency_from", "rate_value"]
            }
        }
    ]
    for t in templates:
        exists = db.query(DataInputTemplate).filter(DataInputTemplate.template_code == t["template_code"]).first()
        if not exists:
            db.add(DataInputTemplate(
                template_code=t["template_code"],
                template_name=t["template_name"],
                target_table=t["target_table"],
                json_schema=t["json_schema"],
                allowed_roles=t["allowed_roles"]
            ))
    db.commit()
    print("Templates seeded.")


def main():
    db = Session()
    try:
        init_users(db)
        init_templates(db)
        print("Initialization complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
