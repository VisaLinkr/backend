# app/routers/applicant_router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from json import dumps

from app.database import get_db
from app.models.models import Applicant, User
from app.schemas.applicant import ApplicantCreate, ApplicantOut, VisaInfoAppend
from app.dependencies.current_user import get_current_user
#from app.models import models  # User 모델

router = APIRouter(prefix="/applicants", tags=["Applicants"])

@router.post("/", response_model=ApplicantOut)
def create_applicant(
    payload: ApplicantCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ORM 방식: JSONB 컬럼은 list로 그대로 넣으면 dialect가 json으로 처리
    obj = Applicant(
        user_id=current_user.id,
        last_name_en=payload.last_name_en,
        first_name_en=payload.first_name_en,
        birth_date=payload.birth_date,
        gender=payload.gender,
        nationality=payload.nationality,
        residence_region=payload.residence_region,
        visa_info=payload.visa_info or [],
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@router.get("/", response_model=List[ApplicantOut])
def list_my_applicants(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Applicant)
        .filter(Applicant.user_id == current_user.id)
        .order_by(Applicant.applicant_id.desc())
        .all()
    )
    return rows

@router.patch("/{applicant_id}/visa-info", response_model=ApplicantOut)
def append_visa_info(
    applicant_id: int,
    payload: VisaInfoAppend,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 본인 소유 레코드인지 확인
    target = (
        db.query(Applicant)
        .filter(Applicant.applicant_id == applicant_id, Applicant.user_id == current_user.id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Applicant not found")

    if not payload.items:
        return target  # 추가할 항목 없으면 그대로 반환

    # JSONB append: visa_info = visa_info || :arr::jsonb
    # SQLAlchemy text로 안전하게 바인딩
    stmt = text("""
        UPDATE applicants
        SET visa_info = visa_info || :arr::jsonb
        WHERE applicant_id = :aid AND user_id = :uid
        RETURNING applicant_id, user_id, last_name_en, first_name_en, birth_date,
                  gender, nationality, residence_region, visa_info, created_at
    """)
    row = db.execute(stmt, {"arr": dumps(payload.items), "aid": applicant_id, "uid": current_user.id}).mappings().first()
    db.commit()
    if not row:
        raise HTTPException(status_code=500, detail="Failed to update visa_info")
    return row