import psycopg2
from psycopg2.extras import execute_values
from datetime import date, timedelta
import random

DB = "postgresql://bi_admin:bi_secret@localhost:5432/bi_dwh"

conn = psycopg2.connect(DB)
cur = conn.cursor()

# Clean old demo data
cur.execute("DELETE FROM fact_transactions WHERE source_system = 'demo'")
cur.execute("DELETE FROM fact_sales WHERE source_system = 'demo'")
cur.execute("DELETE FROM fact_expenses WHERE source_system = 'demo'")
cur.execute("DELETE FROM fact_crm_leads WHERE source_system = 'demo'")
cur.execute("DELETE FROM fact_exchange_rates WHERE source = 'demo'")
conn.commit()

# Get dimension IDs
cur.execute("SELECT account_id, account_code, account_type FROM dim_account")
accounts = {r[1]: r[0] for r in cur.fetchall()}

cur.execute("SELECT currency_id, currency_code FROM dim_currency")
currencies = {r[1]: r[0] for r in cur.fetchall()}

cur.execute("SELECT department_id, department_code FROM dim_department")
depts = {r[1]: r[0] for r in cur.fetchall()}

cur.execute("SELECT employee_id, full_name FROM dim_employee")
employees = [r[0] for r in cur.fetchall()]
if not employees:
    # Seed employees
    emp_seed = [
        ('demo','E001','Александр Иванов',depts.get('SALES'),'Менеджер по продажам','a.ivanov@corp.ru'),
        ('demo','E002','Елена Петрова',depts.get('MARKETING'),'Маркетолог','e.petrova@corp.ru'),
        ('demo','E003','Дмитрий Сидоров',depts.get('PROCUREMENT'),'Закупщик','d.sidorov@corp.ru'),
        ('demo','E004','Ольга Кузнецова',depts.get('ACC'),'Главный бухгалтер','o.kuznetsova@corp.ru'),
        ('demo','E005','Игорь Смирнов',depts.get('IT'),'DevOps инженер','i.smirnov@corp.ru'),
        ('demo','E006','Наталья Васильева',depts.get('ADMIN'),'HR-менеджер','n.vasileva@corp.ru'),
    ]
    execute_values(cur, "INSERT INTO dim_employee (source_system, source_id, full_name, department_id, position_title, email) VALUES %s RETURNING employee_id", emp_seed)
    conn.commit()
    cur.execute("SELECT employee_id FROM dim_employee")
    employees = [r[0] for r in cur.fetchall()]

cur.execute("SELECT counterparty_id, counterparty_name FROM dim_counterparty")
cps = [r[0] for r in cur.fetchall()]
if not cps:
    seed = [
        ('demo',None,'ООО Ромашка','partner','romashka@example.com','+79161234567'),
        ('demo',None,'ИП Иванов','customer','ivanov@example.com','+79169876543'),
        ('demo',None,'ООО Техноснаб','supplier','tehno@example.com','+79161112233'),
        ('demo',None,'ООО Логистик','supplier','log@example.com','+79163334455'),
        ('demo',None,'ООО Маркетинг Про','customer','mp@example.com','+79165556677'),
        ('demo',None,'ИП Петрова','customer','petrova@example.com','+79167778899'),
        ('demo',None,'АО Энергосбыт','supplier','energy@example.com','+79160001122'),
        ('demo',None,'ООО Софтлайн','supplier','soft@example.com','+79162223344'),
    ]
    execute_values(cur, "INSERT INTO dim_counterparty (source_system, source_id, counterparty_name, counterparty_type, email, phone) VALUES %s RETURNING counterparty_id", seed)
    conn.commit()
    cur.execute("SELECT counterparty_id FROM dim_counterparty")
    cps = [r[0] for r in cur.fetchall()]

cur.execute("SELECT product_id, product_name FROM dim_product")
products = [r[0] for r in cur.fetchall()]
if not products:
    seed = [
        ('demo','P001','NB-DELL-001','Ноутбук Dell XPS','Электроника','шт'),
        ('demo','P002','MON-LG-001','Монитор 27\" LG','Электроника','шт'),
        ('demo','P003','FUR-CH-001','Кресло офисное','Мебель','шт'),
        ('demo','P004','PAP-A4-001','Бумага А4 (пачка)','Канцелярия','шт'),
        ('demo','P005','COF-BN-001','Кофе в зернах','Продукты','кг'),
        ('demo','P006','PR-HP-001','Принтер HP','Электроника','шт'),
        ('demo','P007','SRV-DL-001','Услуги доставки','Логистика','усл'),
        ('demo','P008','CON-1C-001','Консультация 1С','Услуги','час'),
    ]
    execute_values(cur, "INSERT INTO dim_product (source_system, source_id, sku, product_name, product_category, unit) VALUES %s RETURNING product_id", seed)
    conn.commit()
    cur.execute("SELECT product_id FROM dim_product")
    products = [r[0] for r in cur.fetchall()]

# Exchange rates (daily for last 12 months)
rates_data = []
base = date(2025,6,1)
for i in range(365):
    d = base - timedelta(days=i)
    rates_data.append((d, 'USD', 'RUB', round(88.5 + random.uniform(-3,3), 4), 'demo'))
    rates_data.append((d, 'EUR', 'RUB', round(96.2 + random.uniform(-3,3), 4), 'demo'))
    rates_data.append((d, 'CNY', 'RUB', round(12.3 + random.uniform(-0.5,0.5), 4), 'demo'))

execute_values(cur, "INSERT INTO fact_exchange_rates (date_id, currency_from, currency_to, rate_value, source) VALUES %s ON CONFLICT DO NOTHING", rates_data)
conn.commit()

# Transactions (revenue + expenses) for last 12 months
transactions = []
base = date(2025,6,11)
for i in range(180):
    d = base - timedelta(days=random.randint(0,330))

    # Revenue transactions ~30%
    if random.random() < 0.30:
        amt = round(random.uniform(50000, 500000), 2)
        transactions.append((
            d, d, d, 'demo-inv-%d' % i, 'invoice',
            accounts['REV-001'], random.choice(cps), random.choice([depts.get('SALES'), depts.get('MARKETING')]),
            random.choice(products), random.choice(employees),
            currencies['RUB'], amt, amt, 0, 20,
            round(random.uniform(1,10),2), round(amt/random.uniform(1,10),2),
            'Продажа %s' % random.choice(['ноутбуков','мониторов','мебели','услуг']),
            'demo', 'demo-%d' % i, False
        ))

    # COGS ~15%
    if random.random() < 0.15:
        amt = round(random.uniform(20000, 250000), 2)
        transactions.append((
            d, d, d, 'demo-cogs-%d' % i, 'delivery_note',
            accounts['COGS-001'], random.choice(cps), depts.get('PROCUREMENT'),
            random.choice(products), random.choice(employees),
            currencies['RUB'], amt, amt, round(amt*0.2,2), 20,
            round(random.uniform(5,50),2), round(amt/random.uniform(5,50),2),
            'Себестоимость %s' % random.choice(['товаров','материалов']),
            'demo', 'demo-cogs-%d' % i, False
        ))

    # OPEX items
    opex_map = [
        ('OPEX-001', 'ФОТ', 80000, 250000),
        ('OPEX-002', 'Аренда', 40000, 120000),
        ('OPEX-003', 'Реклама', 15000, 80000),
        ('OPEX-004', 'Закупки', 10000, 50000),
        ('OPEX-005', 'Канцелярия', 2000, 15000),
        ('OPEX-006', 'Логистика', 5000, 40000),
        ('OPEX-007', 'Связь', 3000, 10000),
        ('OPEX-008', 'Амортизация', 5000, 30000),
    ]
    for acc_code, name, lo, hi in opex_map:
        if random.random() < 0.08:
            amt = round(random.uniform(lo, hi), 2)
            transactions.append((
                d, d, d, 'demo-%s-%d' % (acc_code, i), 'expense_report',
                accounts[acc_code], random.choice(cps), random.choice(list(depts.values())),
                random.choice(products), random.choice(employees),
                currencies['RUB'], amt, amt, round(amt*0.2,2) if random.random()<0.5 else 0, 20,
                None, None,
                '%s за %s' % (name, d.strftime('%B %Y')),
                'demo', 'demo-%s-%d' % (acc_code, i), False
            ))

# Bulk insert transactions
execute_values(cur, """
INSERT INTO fact_transactions (
    transaction_date, posting_date, date_id, document_number, document_type,
    account_id, counterparty_id, department_id, product_id, employee_id,
    currency_id, amount_original, amount_rub, vat_amount, vat_rate,
    quantity, unit_price, description, source_system, source_id, is_manual_entry
) VALUES %s
""", transactions)
conn.commit()

# Sales data for last 12 months
sales = []
statuses = ['won','won','won','won','open','lost']
for i in range(200):
    d = base - timedelta(days=random.randint(0,330))
    close_d = d + timedelta(days=random.randint(1,45)) if random.random() > 0.2 else None
    status = random.choice(statuses)
    amt = round(random.uniform(30000, 400000), 2)
    cost = round(amt * random.uniform(0.45, 0.75), 2)
    margin = amt - cost
    sales.append((
        'demo', 'demo-deal-%d' % i, d, d, close_d,
        random.choice(cps), random.choice(products), random.choice(employees), depts.get('SALES'),
        random.choice(['Входящие','Исходящие холодные','Повторные']), 'Основная воронка',
        status, amt, amt, margin, cost,
        round(random.uniform(60,95),2), random.randint(5,35),
        random.choice(['Крупный заказ','Стандартная сделка','Пилотный проект','Расширение лицензий']),
        False
    ))

execute_values(cur, """
INSERT INTO fact_sales (
    source_system, source_id, deal_date, date_id, close_date,
    counterparty_id, product_id, employee_id, department_id,
    stage_name, pipeline_name, deal_status, amount_original, amount_rub,
    margin_amount_rub, cost_amount_rub, probability_pct, lead_time_days,
    description, is_deleted
) VALUES %s
""", sales)
conn.commit()

# Expenses
expenses = []
categories = [
    ('Канцелярия','Бумага А4', 500, 3000),
    ('Канцелярия','Картриджи', 2000, 8000),
    ('Перевозки','Доставка по Москве', 1500, 12000),
    ('Перевозки','Межгород', 5000, 45000),
    ('Реклама','Яндекс.Директ', 20000, 80000),
    ('Реклама','ВКонтакте', 10000, 40000),
    ('Питание','Кофе и чай', 3000, 8000),
    ('Питание','Корпоративный обед', 5000, 15000),
    ('IT','Лицензии ПО', 10000, 50000),
    ('IT','Хостинг и серверы', 8000, 25000),
]
for i in range(150):
    d = base - timedelta(days=random.randint(0,330))
    cat, item, lo, hi = random.choice(categories)
    amt = round(random.uniform(lo, hi), 2)
    expenses.append((
        d, d, random.choice([accounts['OPEX-005'], accounts['OPEX-003'], accounts['OPEX-006'], accounts['OPEX-007']]),
        random.choice(cps), random.choice(list(depts.values())), random.choice(employees),
        cat, item, currencies['RUB'], amt, amt, 0,
        '%s: %s' % (cat, item), 'demo', False
    ))

execute_values(cur, """
INSERT INTO fact_expenses (
    expense_date, date_id, account_id, counterparty_id, department_id, employee_id,
    expense_category, expense_item, currency_id, amount_original, amount_rub,
    vat_amount, description, source_system, is_manual_entry
) VALUES %s
""", expenses)
conn.commit()

# CRM leads
channels = ['organic','paid','referral','direct','social']
lead_statuses = ['new','qualified','converted','converted','lost']
leads = []
for i in range(300):
    d = base - timedelta(days=random.randint(0,330))
    conv = d + timedelta(days=random.randint(1,20)) if random.random() > 0.4 else None
    leads.append((
        'demo', 'demo-lead-%d' % i, d, d, conv,
        random.choice(cps), random.choice(employees), 'Основная воронка', random.choice(channels),
        random.choice(lead_statuses), random.choice(['yandex','google','vk','direct','referral']),
        random.choice(['cpc','organic','cpm','banner','email']),
        random.choice(['summer2025','promo_q2','brand_search','retargeting']),
        False
    ))

execute_values(cur, """
INSERT INTO fact_crm_leads (
    source_system, source_id, created_date, date_id, converted_date,
    counterparty_id, employee_id, pipeline_name, source_channel,
    lead_status, utm_source, utm_medium, utm_campaign, is_deleted
) VALUES %s
""", leads)
conn.commit()

cur.close()
conn.close()
print('Demo data inserted successfully!')
print('Transactions:', len(transactions))
print('Sales:', len(sales))
print('Expenses:', len(expenses))
print('Leads:', len(leads))
print('Exchange rates:', len(rates_data))
