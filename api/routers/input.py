from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import text
from deps import get_db, get_current_user, require_role
from models import BiUser, FactExpense, FactTransaction, DataInputEntry, DataInputTemplate, DimCurrency
from schemas import ExpenseCreate, ExpenseOut, TransactionCreate, TransactionOut, DataInputSubmit, DataInputOut
from services.file_import_service import import_file_to_staging, list_uploads, get_staging_rows
from routers.auth import create_access_token

router = APIRouter()


def _convert_to_rub(db: Session, amount: float, currency_id: int, tx_date: date) -> float:
    if currency_id == 1:  # RUB
        return amount
    row = db.execute(text("""
        SELECT rate_value FROM fact_exchange_rates
        WHERE date_id <= :d AND currency_from = (SELECT currency_code FROM dim_currency WHERE currency_id = :cid)
        ORDER BY date_id DESC LIMIT 1
    """), {"d": tx_date, "cid": currency_id}).fetchone()
    if row:
        return float(amount) * float(row[0])
    raise HTTPException(status_code=400, detail=f"No exchange rate found for currency {currency_id} on {tx_date}")


@router.post("/expenses", response_model=ExpenseOut)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    user: BiUser = Depends(get_current_user)
):
    amount_rub = _convert_to_rub(db, float(payload.amount_original), payload.currency_id, payload.expense_date)
    expense = FactExpense(
        expense_date=payload.expense_date,
        date_id=payload.expense_date,
        account_id=payload.account_id,
        department_id=payload.department_id,
        employee_id=payload.employee_id,
        expense_category=payload.expense_category,
        expense_item=payload.expense_item,
        currency_id=payload.currency_id,
        amount_original=payload.amount_original,
        amount_rub=amount_rub,
        description=payload.description,
        receipt_info=payload.receipt_info,
        source_system="manual_api",
        is_manual_entry=True,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.post("/transactions", response_model=TransactionOut)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    user: BiUser = Depends(get_current_user)
):
    posting = payload.posting_date or payload.transaction_date
    amount_rub = _convert_to_rub(db, float(payload.amount_original), payload.currency_id, posting)
    tx = FactTransaction(
        transaction_date=payload.transaction_date,
        posting_date=posting,
        date_id=posting,
        account_id=payload.account_id,
        counterparty_id=payload.counterparty_id,
        department_id=payload.department_id,
        currency_id=payload.currency_id,
        amount_original=payload.amount_original,
        amount_rub=amount_rub,
        description=payload.description,
        source_system="manual_api",
        is_manual_entry=True,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


@router.post("/submit", response_model=DataInputOut)
def submit_entry(
    payload: DataInputSubmit,
    db: Session = Depends(get_db),
    user: BiUser = Depends(get_current_user)
):
    tmpl = db.query(DataInputTemplate).filter(
        DataInputTemplate.template_code == payload.template_code,
        DataInputTemplate.is_active == True
    ).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    if user.role not in tmpl.allowed_roles:
        raise HTTPException(status_code=403, detail="You are not allowed to submit this form")
    entry = DataInputEntry(
        template_id=tmpl.template_id,
        submitted_by=user.username,
        entry_data=payload.entry_data,
        status="submitted"
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/entries", response_model=list[DataInputOut])
def list_entries(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin","cfo","ceo"))
):
    q = db.query(DataInputEntry)
    if status:
        q = q.filter(DataInputEntry.status == status)
    return q.order_by(DataInputEntry.submitted_at.desc()).limit(200).all()


@router.post("/upload")
def upload_file(
    target_table: str = Form(...),
    notes: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "cfo", "manager"))
):
    return import_file_to_staging(db, file, target_table, user.username, notes)


@router.get("/uploads")
def uploads_list(
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "cfo", "manager"))
):
    return list_uploads(db, uploaded_by=user.username if user.role == "manager" else None)


@router.get("/uploads/{upload_id}/rows")
def upload_rows(
    upload_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "cfo", "manager"))
):
    return get_staging_rows(db, upload_id, status=status)
