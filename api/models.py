from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, Date, DateTime, Text, ForeignKey, JSON, ARRAY
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class DimCurrency(Base):
    __tablename__ = "dim_currency"
    currency_id = Column(Integer, primary_key=True)
    currency_code = Column(String(3), unique=True, nullable=False)
    currency_name = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DimDepartment(Base):
    __tablename__ = "dim_department"
    department_id = Column(Integer, primary_key=True)
    department_name = Column(String(100), nullable=False)
    department_code = Column(String(20), unique=True)
    parent_department_id = Column(Integer, ForeignKey("dim_department.department_id"))
    manager_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DimEmployee(Base):
    __tablename__ = "dim_employee"
    employee_id = Column(Integer, primary_key=True)
    source_system = Column(String(50), nullable=False)
    source_id = Column(String(255))
    full_name = Column(String(255), nullable=False)
    department_id = Column(Integer, ForeignKey("dim_department.department_id"))
    position_title = Column(String(100))
    email = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DimAccount(Base):
    __tablename__ = "dim_account"
    account_id = Column(Integer, primary_key=True)
    account_code = Column(String(20), unique=True, nullable=False)
    account_name = Column(String(255), nullable=False)
    account_type = Column(String(50), nullable=False)
    parent_account_id = Column(Integer, ForeignKey("dim_account.account_id"))
    pnl_section = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DimDate(Base):
    __tablename__ = "dim_date"
    date_id = Column(Integer, primary_key=True)
    full_date = Column(Date, nullable=False, unique=True)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    month_name = Column(String(20))
    day = Column(Integer, nullable=False)
    weekday = Column(Integer, nullable=False)
    week_of_year = Column(Integer)
    is_weekend = Column(Boolean, default=False)
    fiscal_year = Column(Integer)
    fiscal_quarter = Column(Integer)


class DimCounterparty(Base):
    __tablename__ = "dim_counterparty"
    counterparty_id = Column(Integer, primary_key=True)
    source_system = Column(String(50), nullable=False)
    source_id = Column(String(255), nullable=False)
    counterparty_name = Column(String(255), nullable=False)
    counterparty_type = Column(String(50), default="client")
    inn = Column(String(20))
    kpp = Column(String(20))
    email = Column(String(255))
    phone = Column(String(50))
    country = Column(String(100))
    city = Column(String(100))
    address = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DimProduct(Base):
    __tablename__ = "dim_product"
    product_id = Column(Integer, primary_key=True)
    source_system = Column(String(50), nullable=False)
    source_id = Column(String(255), nullable=False)
    sku = Column(String(100))
    product_name = Column(String(255), nullable=False)
    category = Column(String(100))
    brand = Column(String(100))
    unit = Column(String(20))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BiUser(Base):
    __tablename__ = "bi_users"
    user_id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255))
    full_name = Column(String(255))
    role = Column(String(50), default="viewer")
    department_id = Column(Integer, ForeignKey("dim_department.department_id"))
    employee_id = Column(Integer, ForeignKey("dim_employee.employee_id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FactTransaction(Base):
    __tablename__ = "fact_transactions"
    transaction_id = Column(Integer, primary_key=True)
    transaction_date = Column(Date, nullable=False)
    posting_date = Column(Date, nullable=False)
    date_id = Column(Date, ForeignKey("dim_date.date_id"), nullable=False)
    document_number = Column(String(100))
    document_type = Column(String(50), default="unknown")
    account_id = Column(Integer, ForeignKey("dim_account.account_id"), nullable=False)
    counterparty_id = Column(Integer, ForeignKey("dim_counterparty.counterparty_id"))
    department_id = Column(Integer, ForeignKey("dim_department.department_id"))
    product_id = Column(Integer, ForeignKey("dim_product.product_id"))
    employee_id = Column(Integer, ForeignKey("dim_employee.employee_id"))
    currency_id = Column(Integer, ForeignKey("dim_currency.currency_id"), nullable=False)
    amount_original = Column(Numeric(18, 4), nullable=False)
    amount_rub = Column(Numeric(18, 4), nullable=False)
    vat_amount = Column(Numeric(18, 4), default=0)
    vat_rate = Column(Numeric(5, 2), default=0)
    quantity = Column(Numeric(18, 4))
    unit_price = Column(Numeric(18, 4))
    description = Column(Text)
    source_system = Column(String(50), nullable=False)
    source_id = Column(String(255))
    is_manual_entry = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FactExpense(Base):
    __tablename__ = "fact_expenses"
    expense_id = Column(Integer, primary_key=True)
    expense_date = Column(Date, nullable=False)
    date_id = Column(Date, ForeignKey("dim_date.date_id"), nullable=False)
    account_id = Column(Integer, ForeignKey("dim_account.account_id"), nullable=False)
    counterparty_id = Column(Integer, ForeignKey("dim_counterparty.counterparty_id"))
    department_id = Column(Integer, ForeignKey("dim_department.department_id"))
    employee_id = Column(Integer, ForeignKey("dim_employee.employee_id"))
    expense_category = Column(String(100), nullable=False)
    expense_item = Column(String(255), nullable=False)
    currency_id = Column(Integer, ForeignKey("dim_currency.currency_id"), nullable=False)
    amount_original = Column(Numeric(18, 4), nullable=False)
    amount_rub = Column(Numeric(18, 4), nullable=False)
    vat_amount = Column(Numeric(18, 4), default=0)
    description = Column(Text)
    receipt_info = Column(String(255))
    source_system = Column(String(50), nullable=False)
    is_manual_entry = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlertRule(Base):
    __tablename__ = "alert_rules"
    rule_id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    metric_name = Column(String(100), nullable=False)
    condition = Column(String(50), nullable=False)
    threshold_value = Column(Numeric(18, 4), nullable=False)
    lookback_days = Column(Integer, default=7)
    severity = Column(String(20), default="warning")
    schedule = Column(String(20), default="daily")
    roles = Column(ARRAY(String))
    is_active = Column(Boolean, default=True)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlertHistory(Base):
    __tablename__ = "alerts_history"
    alert_id = Column(Integer, primary_key=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.rule_id"), nullable=True)
    metric_name = Column(String(100))
    metric_value = Column(Numeric(18, 4))
    threshold_value = Column(Numeric(18, 4))
    message = Column(Text, nullable=False)
    severity = Column(String(20))
    channels = Column(ARRAY(String))
    status = Column(String(20), default="new")
    acknowledged_by = Column(String(100))
    acknowledged_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    audit_id = Column(Integer, primary_key=True)
    table_name = Column(String(100), nullable=False)
    record_id = Column(Integer, nullable=False)
    action = Column(String(20), nullable=False)
    changed_by = Column(String(255), nullable=False)
    changed_at = Column(DateTime, default=datetime.utcnow)
    old_values = Column(JSON)
    new_values = Column(JSON)
    reason = Column(Text)


class EtlRun(Base):
    __tablename__ = "etl_runs"
    run_id = Column(Integer, primary_key=True)
    etl_name = Column(String(100), nullable=False)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime)
    status = Column(String(20), nullable=False, default="running")
    records_processed = Column(Integer, default=0)
    records_inserted = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    error_message = Column(Text)
    log_output = Column(Text)


class DataInputEntry(Base):
    __tablename__ = "data_input_entries"
    entry_id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("data_input_templates.template_id"), nullable=False)
    submitted_by = Column(String(255), nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    entry_data = Column(JSON, nullable=False)
    validation_errors = Column(JSON)
    status = Column(String(20), default="draft")
    applied_at = Column(DateTime)
    applied_by = Column(String(255))
    rejection_reason = Column(Text)


class DataInputTemplate(Base):
    __tablename__ = "data_input_templates"
    template_id = Column(Integer, primary_key=True)
    template_code = Column(String(50), unique=True, nullable=False)
    template_name = Column(String(255), nullable=False)
    target_table = Column(String(100), nullable=False)
    json_schema = Column(JSON, nullable=False)
    allowed_roles = Column(ARRAY(String(50)), default=["admin"])
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CashflowForecast(Base):
    __tablename__ = "cashflow_forecasts"
    forecast_id = Column(Integer, primary_key=True)
    forecast_date = Column(Date, nullable=False)
    metric_type = Column(String(20), nullable=False)
    predicted_value = Column(Numeric(18, 4), nullable=False)
    lower_bound = Column(Numeric(18, 4), nullable=False)
    upper_bound = Column(Numeric(18, 4), nullable=False)
    model_name = Column(String(50), nullable=False)
    is_forecast = Column(Boolean, default=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
