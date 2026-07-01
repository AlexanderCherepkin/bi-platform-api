from decimal import Decimal
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from pydantic import BaseModel, Field, EmailStr, ConfigDict


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserLogin(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None
    role: str = "viewer"
    department_id: Optional[int] = None


class UserOut(BaseModel):
    user_id: int
    username: str
    email: str
    full_name: Optional[str] = None
    role: str
    department_id: Optional[int] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ExpenseCreate(BaseModel):
    expense_date: date
    account_id: int
    department_id: Optional[int] = None
    employee_id: Optional[int] = None
    expense_category: str = Field(..., min_length=1, max_length=100)
    expense_item: str = Field(..., min_length=1, max_length=255)
    currency_id: int
    amount_original: Decimal = Field(..., gt=0)
    description: Optional[str] = None
    receipt_info: Optional[str] = None


class ExpenseOut(BaseModel):
    expense_id: int
    expense_date: date
    account_id: int
    amount_original: Decimal
    amount_rub: Decimal
    expense_category: str
    expense_item: str
    is_manual_entry: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionCreate(BaseModel):
    transaction_date: date
    posting_date: Optional[date] = None
    account_id: int
    counterparty_id: Optional[int] = None
    department_id: Optional[int] = None
    currency_id: int
    amount_original: Decimal = Field(..., gt=0)
    description: Optional[str] = None


class TransactionOut(BaseModel):
    transaction_id: int
    transaction_date: date
    account_id: int
    amount_original: Decimal
    amount_rub: Decimal
    source_system: str
    is_manual_entry: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DataInputSubmit(BaseModel):
    template_code: str
    entry_data: Dict[str, Any]


class DataInputOut(BaseModel):
    entry_id: int
    template_id: int
    submitted_by: str
    submitted_at: datetime
    entry_data: Dict[str, Any]
    status: str
    applied_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PnlSummary(BaseModel):
    year: int
    month: int
    revenue: Decimal
    cogs: Decimal
    gross_profit: Decimal
    opex: Decimal
    operating_profit: Decimal
    tax: Decimal
    net_profit: Decimal
    gross_margin_pct: Optional[Decimal] = None
    operating_margin_pct: Optional[Decimal] = None
    net_margin_pct: Optional[Decimal] = None


class PnlWaterfallItem(BaseModel):
    label: str
    value: Decimal
    is_total: bool
    is_negative: bool


class BudgetVsActualItem(BaseModel):
    year: int
    month: int
    account_id: int
    account_code: str
    account_name: str
    account_type: str
    actual_amount_rub: Decimal
    budget_amount_rub: Decimal
    variance_amount_rub: Decimal
    variance_pct: Optional[Decimal] = None
