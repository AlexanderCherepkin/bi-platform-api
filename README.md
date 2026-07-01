# BI Platform

Корпоративная система бизнес-аналитики (BI) и управленческой отчетности.

## Deploy to Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/AlexanderCherepkin/bi-platform-api)

Click the button above to provision a free PostgreSQL database and a Docker web
service for the FastAPI backend. After the first deploy, open the Render Shell
for `bi-platform-api` and run `python scripts/init_remote_db.py` to seed demo users.

Then set the backend URL in your Vercel frontend environment variables:
`API_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`, `API_USER`, `API_PASS`.
See `DEPLOY.md` for the full checklist.

## Архитектура

- **DWH:** PostgreSQL 16 (реляционное хранилище данных)
- **BI:** Metabase (open-source, self-hosted) + встроенные Next.js отчёты
- **ETL:** Python (SQLAlchemy, httpx, APScheduler) с Redis-блокировками и кэшем метрик
- **Frontend:** Next.js 16 App Router + Tailwind CSS + Recharts
- **Input UI:** FastAPI + Next.js формы
- **Infra:** Docker + Docker Compose

## Быстрый старт

```bash
cd bi_platform
cp .env.example .env
# Отредактируйте .env под себя
docker compose up -d
make init
make bootstrap-metabase
make metabase-embed
```

- Next.js UI: http://localhost:3000
- Metabase: http://localhost:3001
- API docs: http://localhost:8000/docs
- PostgreSQL: localhost:5432

## Структура проекта

```
bi_platform/
├── docker-compose.yml
├── .env.example
├── Makefile
├── db/
│   ├── migrations/          # SQL-миграции (выполняются при старте Postgres)
│   └── seeds/               # Тестовые/начальные данные
├── etl/
│   ├── config.py            # Настройки ETL
│   ├── extractors/          # Коннекторы к 1С, amoCRM, Google Sheets
│   ├── transformers/        # Трансформации в staging/fact
│   ├── loaders/             # Загрузка в fact-таблицы
│   ├── runners/             # Оркестрация синхронизации
│   └── scheduler.py         # APScheduler фоновые задачи
├── api/
│   ├── main.py              # FastAPI приложение
│   ├── models.py            # SQLAlchemy модели
│   ├── schemas.py           # Pydantic схемы
│   ├── routers/             # Эндпоинты (metrics, etl, db, ...)
│   └── Dockerfile
├── scripts/
│   ├── setup_metabase.py    # Базовая настройка Metabase
│   └── setup_metabase_embed.py  # Создание embedded дашборда
├── vercel-app/              # Next.js frontend
│   ├── src/app/             # App Router страницы
│   └── src/components/      # UI компоненты
└── docs/
    └── runbook.md           # Инструкция для пользователей
```

## Аутентификация и RBAC

Frontend получает JWT от FastAPI (`/auth/token`) и хранит `access_token` в `localStorage`. Роль пользователя (`admin`, `ceo`, `cfo`, `sales_head`, `manager`, `viewer`) извлекается из токена на клиенте и используется для скрытия пунктов меню и защиты роутов.

- Страница входа: `/login`
- API-прокси Next.js: `vercel-app/src/app/api/auth/token/route.ts`
- Компоненты: `AuthProvider`, `RoleGate`, `useAuth`
- Фильтрация навигации и главной страницы по ролям

Защищённые роуты:
- `/dashboard` — `admin`, `ceo`, `cfo`
- `/embedded-reports` — `admin`, `ceo`, `cfo`, `sales_head`
- `/db-overview` — `admin`, `cfo`, `sales_head`, `manager`
- `/sql-query` — `admin`, `cfo`, `sales_head`, `manager`
- `/data-input` — `admin`, `cfo`, `sales_head`, `manager`
- `/sales-funnel` — `admin`, `ceo`, `sales_head`
- `/managers` — `admin`, `ceo`, `sales_head`
- `/pnl-waterfall` — `admin`, `ceo`, `cfo`
- `/budget-vs-actual` — `admin`, `ceo`, `cfo`

Тестовые пользователи (создаются `make init`):
- `admin` / `admin123`
- `ceo` / `ceo123`
- `cfo` / `cfo123`
- `sales_head` / `sales123`
- `manager1` / `manager123`

## Встроенная аналитика

Страница `/embedded-reports` отображает публичный дашборд Metabase "Executive Overview" через iframe — self-service аналитика без SQL. Bootstrap: `make metabase-embed`.

## Drill-down с дашборда

На `/dashboard` графики P&L и Cashflow стали кликабельными. Клик по столбцу месяца открывает `/db-overview/transactions?year=YYYY&month=MM` — список транзакций `fact_transactions` за выбранный период с суммой в рублях и источником данных. Это даёт быстрый drill-down от агрегированного показателя к проводкам без написания SQL.

Реализация:
- `src/components/dashboard/pnl-chart.tsx` / `cashflow-chart.tsx` — `onDrill` callback и `pointer` курсор на столбцах.
- `src/app/dashboard/page.tsx` — роутинг на `/db-overview/transactions?year=&month=`.
- `src/app/db-overview/transactions/page.tsx` — страница детальных транзакций с фильтром по дате и JOIN к справочникам счетов/валют.
- `api/routers/db.py` и `src/lib/api.ts` — поддержка параметризованных SQL-запросов (`:start` / `:end`).

## Глобальные фильтры дашборда

На `/dashboard` добавлена панель фильтров: период (год/месяц «с» и «по»), департамент, контрагент, валюта, менеджер. При изменении любого фильтра одновременно пересчитываются все виджеты: KPI-карточки, график P&L, график Cashflow и таблица P&L.

Реализация:
- `src/components/dashboard/dashboard-filters.tsx` — UI панели фильтров и загрузка справочников через `/api/db/dimensions`.
- `src/app/api/metrics/route.ts` — пробрасывает query-параметры в FastAPI `/metrics/pnl` и `/metrics/cashflow`.
- `api/routers/metrics.py` — новые параметры `year_from`, `year_to`, `month_from`, `month_to`, `department_id`, `counterparty_id`, `currency_id`, `employee_id` для динамической фильтрации агрегатов.
- `api/routers/db.py` — эндпоинт `/db/dimensions` для справочников фильтров.

## Backend Spec Bridge / OpenAPI

FastAPI публикует `/openapi.json` и `/docs`. Генератор `scripts/generators/openapi_to_typescript.py` синхронизирует схемы с frontend:

- `vercel-app/src/lib/api/generated/types.ts` — TypeScript-интерфейсы из Pydantic-моделей.
- `vercel-app/src/lib/api/generated/actions.ts` — Next.js Server Actions (`'use server'`) для вызова FastAPI эндпоинтов.

Сгенерированные actions автоматически ставят `Content-Type: application/json` для JSON-тела и используют service-account авторизацию (`apiFetch`). Формы на `/data-input` отправляют типизированные данные через `post_input_expenses` и `post_input_transactions` вместо прямых SQL-вставок.

Перегенерация:

```bash
python scripts/generators/openapi_to_typescript.py \
    --input scripts/openapi.json \
    --types-out vercel-app/src/lib/api/generated/types.ts \
    --actions-out vercel-app/src/lib/api/generated/actions.ts
```

## Воронка продаж и KPI менеджеров

Страница `/sales-funnel` показывает воронку продаж из представления `vw_sales_funnel`:
- фильтры по году и месяцу;
- график количества сделок по этапам;
- график сумм воронки с разбивкой Won / Lost;
- таблица детализации по периоду, воронке, этапу и статусу.

Страница `/managers` отображает KPI продажников из `vw_kpi_sales_managers`:
- фильтры по году и месяцу;
- график выручки по менеджерам (общая сумма + Won);
- комбинированный график win-rate и маржинальности;
- таблица сделок, win-rate, маржи и департамента.

Реализация:
- `src/app/sales-funnel/page.tsx` и `src/app/managers/page.tsx` — страницы с Recharts-визуализацией.
- `src/app/api/metrics/sales-funnel/route.ts` и `src/app/api/metrics/kpi/managers/route.ts` — Next.js прокси к FastAPI.
- `api/routers/metrics.py` — эндпоинты `/metrics/sales-funnel` и `/metrics/kpi/managers` с фильтрами `year` и `month`.
- `src/components/layout/sidebar.tsx` и `src/app/page.tsx` — навигация и карточки для ролей `admin`, `ceo`, `sales_head`.

## Waterfall P&L

Страница `/pnl-waterfall` визуализирует `vw_pnl_waterfall` в виде водопадного графика:
Выручка → COGS → Валовая прибыль → OPEX → Операционная прибыль → Прочие доходы/расходы → Налог → Чистая прибыль.

- фильтры по году и месяцу;
- итоговые статьи отображаются синими столбцами от нуля;
- расходы — красные столбцы, понижающие накопленный итог;
- доходы — зелёные столбцы, повышающие накопленный итог;
- таблица детализации с типом каждой статьи.

Реализация:
- `src/app/pnl-waterfall/page.tsx` — страница с фильтрами и таблицей.
- `src/components/dashboard/waterfall-chart.tsx` — водопадный график на Recharts через stacked bars.
- `src/app/api/metrics/pnl-waterfall/route.ts` — Next.js прокси.
- `api/routers/metrics.py` — эндпоинт `/metrics/pnl-waterfall` и схема `PnlWaterfallItem`.
- Навигация и карточка на главной для ролей `admin`, `ceo`, `cfo`.

## Бюджет vs Факт

Добавлена таблица `budget_monthly`, представление `vw_budget_vs_actual` и страница `/budget-vs-actual`.

- `budget_monthly` хранит месячный бюджет по счёту (`account_id`) и опциональному департаменту (`department_id`).
- `vw_budget_vs_actual` объединяет факт из `fact_transactions` с бюджетом и считает отклонение в сумме и процентах.
- Страница `/budget-vs-actual` доступна ролям `admin`, `ceo`, `cfo`:
  - фильтры по году и месяцу;
  - группированный bar-график «Бюджет vs Факт» по счетам;
  - таблица с периодом, счётом, бюджетом, фактом, отклонением и отклонением %.

Реализация:
- `db/migrations/004_budget_monthly.sql` — таблица, представление и демо-данные бюджета.
- `api/routers/metrics.py` — эндпоинт `/metrics/budget-vs-actual` и схема `BudgetVsActualItem`.
- `src/app/api/metrics/budget-vs-actual/route.ts` — Next.js прокси.
- `src/app/budget-vs-actual/page.tsx` — страница с графиком и таблицей.
- Навигация в `sidebar.tsx` и карточка на `page.tsx` для ролей `admin`, `ceo`, `cfo`.

## Real-time обновление метрик (SSE)

Дашборд `/dashboard` и страница `/budget-vs-actual` автоматически перезагружают метрики при изменении данных в `fact_transactions` и `fact_expenses` — без ручного обновления страницы.

Поток событий:
1. `AFTER INSERT OR UPDATE OR DELETE` триггеры на `fact_transactions` и `fact_expenses` вызывают `pg_notify('metrics_update', ...)`.
2. FastAPI-сервис `api/realtime.py` слушает PostgreSQL через `asyncpg` и рассылает SSE-событие `metrics_update` всем подключённым клиентам.
3. При получении события инвалидация Redis-кеша `metrics:*`, чтобы следующий запрос метрик вернул свежие данные.
4. Next.js-прокси `vercel-app/src/app/api/realtime/metrics/route.ts` передаёт SSE-поток в браузер (решает ограничение `EventSource` с заголовком Authorization).
5. `createRealtimeStream` на страницах `/dashboard` и `/budget-vs-actual` вызывает `loadMetrics()` / `loadData()` при событии `metrics_update`.

Индикатор `Live` в шапке страницы показывает зелёный пульсирующий статус при активном SSE-соединении и серый — при обрыве.

Реализация:
- `db/migrations/005_realtime_notify.sql` — триггеры и функция `fn_notify_metrics_update()`.
- `api/realtime.py` — `asyncpg` LISTEN, in-memory broadcast bus, инвалидация `metrics:*` кеша.
- `api/routers/realtime.py` — SSE endpoint `/realtime/metrics`.
- `etl/utils/cache.py` — `delete_pattern()` для удаления ключей по маске.
- `vercel-app/src/lib/realtime.ts` — обёртка `EventSource` с обработкой событий `connected`, `metrics_update`, `heartbeat`.
- `vercel-app/src/components/ui/live-indicator.tsx` — React-компонент индикатора.
- `vercel-app/src/app/api/realtime/metrics/route.ts` — Next.js прокси SSE.
- `vercel-app/src/app/dashboard/page.tsx` и `vercel-app/src/app/budget-vs-actual/page.tsx` — подписка на поток и перезагрузка данных.

> **Ограничение:** in-memory broadcast bus работает только внутри одного воркера FastAPI. Для multi-worker-деплоя замените шину на Redis pub/sub.

## Алерты и аномалии

Система периодически проверяет финансовые метрики и уведомляет ответственных ролей (`admin`, `ceo`, `cfo`) через UI и Telegram.

Правила хранятся в таблице `alert_rules` и управляются из БД (без хардкода):
- **Падение выручки >20%** — сравнение скользящего 7-дневного окна с аналогичным периодом неделей ранее (WoW), проверяется ежедневно в 09:00.
- **Отрицательный cashflow** — чистый cashflow за последние сутки ниже 0, проверяется каждый час.
- **Рост OPEX >15%** — сравнение 30-дневного окна с предыдущим месячным периодом (MoM), проверяется ежедневно в 09:00.

Каналы уведомлений:
- **UI:** иконка «Колокольчик» в шапке с бейджем непрочитанных алертов; страница `/alerts` со списком истории и кнопкой «Подтвердить».
- **Telegram:** отправка в указанный `TELEGRAM_CHAT_ID` через `TELEGRAM_BOT_TOKEN`.
- **SSE:** при срабатывании правила сервер широковещательно рассылает событие `alert` всем активным клиентам, и браузер показывает всплывающее уведомление.

Реализация:
- `db/migrations/006_alert_rules.sql` — таблицы `alert_rules` и `alerts_history`, три дефолтных правила.
- `api/models.py` — ORM-модели `AlertRule`, `AlertHistory`.
- `api/services/alerts_service.py` — вычисление метрик, проверка условий, дедупликация (4 часа), отправка Telegram/SSE.
- `api/routers/alerts.py` — REST для управления правилами и историей.
- `etl/scheduler.py` — APScheduler job'ы `alerts_daily` (09:00) и `alerts_hourly`.
- `vercel-app/src/components/ui/alert-bell.tsx` и `vercel-app/src/components/layout/header.tsx` — колокольчик в шапке.
- `vercel-app/src/app/alerts/page.tsx` — страница истории алертов.
- `vercel-app/src/lib/realtime.ts` — обработка SSE-события `alert`.
- `vercel-app/src/app/api/alerts/*` — Next.js прокси к FastAPI.

Настройка Telegram: заполните `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` в `.env`.

## Экспорт и отчёты

Добавлены клиентские кнопки экспорта для таблиц и PDF-отчёт для дашборда:

- **CSV / Excel** — на всех табличных представлениях (`/dashboard`, `/db-overview/transactions`, `/db-overview/[schema]/[table]`, `/sql-query`). Данные выгружаются через `xlsx` и `file-saver` без участия сервера.
- **PDF дашборда** — кнопка «Скачать PDF» на `/dashboard` делает скриншот контейнера через `html2canvas` и сохраняет одностраничный PDF через `jsPDF`.

Реализация:
- `vercel-app/src/lib/export.ts` — универсальные функции `exportCsv`, `exportExcel`, `exportDashboardPdf`.
- `vercel-app/src/components/ui/export-buttons.tsx` — компонент с кнопками CSV/Excel.
- `vercel-app/src/components/db-overview/data-table.tsx` — поддержка `title`/`filename` для отображения заголовка и кнопок экспорта.
- `vercel-app/src/app/dashboard/page.tsx` — ref на `<main>` и кнопка «Скачать PDF».

## Этапы реализации

1. **Аудит + архитектура** — карта источников, схема DWH, выбор метрик.
2. **MVP** — DWH, ETL для 1С + Google Sheets + amoCRM, финансовый дашборд (P&L, Cashflow), Metabase embed.
3. **Полное внедрение** — RBAC, drill-down, self-service импорт, мониторинг качества данных.
4. **Поддержка** — мониторинг, документация, обучение.

## Лицензия

Внутренний проект компании. NDA.
