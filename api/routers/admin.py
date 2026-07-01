from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from deps import get_db, require_role
from models import BiUser, DataInputEntry
from schemas import UserCreate, UserOut

router = APIRouter()


@router.get("/users", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db),
    admin: BiUser = Depends(require_role("admin"))
):
    return db.query(BiUser).all()


@router.post("/users/{user_id}/activate")
def activate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: BiUser = Depends(require_role("admin"))
):
    user = db.query(BiUser).filter(BiUser.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    db.commit()
    return {"detail": "User activated"}


@router.post("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: BiUser = Depends(require_role("admin"))
):
    user = db.query(BiUser).filter(BiUser.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.commit()
    return {"detail": "User deactivated"}


@router.post("/entries/{entry_id}/approve")
def approve_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    admin: BiUser = Depends(require_role("admin", "cfo"))
):
    entry = db.query(DataInputEntry).filter(DataInputEntry.entry_id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry.status = "applied"
    entry.applied_at = text("NOW()")
    entry.applied_by = admin.username
    db.commit()
    return {"detail": "Entry approved and applied"}


@router.post("/entries/{entry_id}/reject")
def reject_entry(
    entry_id: int,
    reason: str,
    db: Session = Depends(get_db),
    admin: BiUser = Depends(require_role("admin", "cfo"))
):
    entry = db.query(DataInputEntry).filter(DataInputEntry.entry_id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry.status = "rejected"
    entry.rejection_reason = reason
    db.commit()
    return {"detail": "Entry rejected"}
