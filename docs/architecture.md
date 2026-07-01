# Архитектура BI-системы

## Логические слои

```
┌─────────────────────────────────────────────────────────────┐
│  Presentation Layer                                         │
│  • Metabase (дашборды)                                      │
│  • FastAPI + Swagger (ввод данных, REST)                    │
├─────────────────────────────────────────────────────────────┤
│  Analytics / Semantic Layer                                 │
│  • PostgreSQL Views (vw_pnl_waterfall, vw_cashflow_monthly) │
│  • Row-Level Security (будет настроена в Metabase)          │
├─────────────────────────────────────────────────────────────┤
│  DWH — Fact & Dimension Tables                             │
│  • fact_transactions, fact_sales, fact_expenses            │
│  • fact_crm_leads, fact_exchange_rates                     │
│  • dim_date, dim_currency, dim_counterparty, dim_account   │
├─────────────────────────────────────────────────────────────┤
│  Staging Layer                                              │
│  • staging.stg_amocrm_leads / deals                        │
│  • staging.stg_1c_transactions                             │
│  • staging.stg_gsheets_expenses                            │
├─────────────────────────────────────────────────────────────┤
│  ETL / Integration Layer                                  │
│  • Python connectors (amoCRM, 1C OData, Google Sheets API)  │
│  • Cleansing (dates, currencies, dedup)                    │
│  • Currency conversion (CBRF rates)                        │
│  • Orchestration: cron / Airflow (Phase 2)                  │
├─────────────────────────────────────────────────────────────┤
│  Source Systems                                             │
│  • amoCRM (REST API)                                        │
│  • 1C:Управление торговлей (OData / webhooks)               │
│  • Google Sheets (3 таблицы расходов)                       │
│  • Ручной ввод (FastAPI UI)                                 │
└─────────────────────────────────────────────────────────────┘
```

## Технологический стек

| Компонент | Технология | Обоснование |
|---|---|---|
| DWH | PostgreSQL 16 | Знакомый стек, отличная поддержка JSONB, бесплатный |
| BI | Metabase | Open-source, self-hosted, нет оплаты за пользователя |
| API / Backend | FastAPI + SQLAlchemy | Высокая производительность, автогенерация docs |
| ETL | Python (pandas, httpx) | Универсальность, скорость разработки |
| Контейнеры | Docker + Docker Compose | Простота деплоя без DevOps-команды |
| Инфраструктура | Yandex Cloud / Reg.ru VPS | Данные в РФ, предсказуемая стоимость |

## Безопасность и RBAC

- Аутентификация: JWT через FastAPI OAuth2.
- Роли: admin, ceo, cfo, sales_head, manager, viewer.
- Metabase: группы пользователей + фильтры на уровне дашбордов (Row-Level Security через переменные).
- Аудит: таблица `audit_log` фиксирует INSERT/UPDATE/DELETE в `fact_transactions`.

## План развертывания

1. Подготовить VPS (Ubuntu 22.04 LTS, 2 vCPU, 4 GB RAM, 40 GB SSD).
2. Установить Docker + Docker Compose.
3. Скопировать `bi_platform/` на сервер.
4. `cp .env.example .env` → заполнить реальные ключи API.
5. `docker compose up -d`.
6. Запустить `python scripts/init_db.py` и `python scripts/setup_metabase.py`.
7. Открыть Metabase, настроить дашборд из SQL-файла `metabase/dashboard_financial.sql`.
8. Проверить ETL: `python -m etl.runners.sync --sources rates,gsheets`.

## Масштабирование

- До 100k строк/месяц текущая схема на PostgreSQL держится без проблем.
- При росте >500k строк/месяц можно перейти на TimescaleDB или ClickHouse.
- ETL при росте источников мигрирует на Apache Airflow.
