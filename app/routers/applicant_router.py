# app/routers/applicant_router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.models import Applicant, User
from app.schemas.applicant import ApplicantCreate, ApplicantOut, VisaInfoAppend
from app.dependencies.current_user import get_current_user

router = APIRouter(prefix="/applicants", tags=["Applicants"])

def _clean_str_or_none(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v2 = v.strip()
    return v2 if v2 else None

def _clean_list_str(items: Optional[List[str]]) -> List[str]:
    if not items:
        return []
    return [s.strip() for s in items if isinstance(s, str) and s.strip()]

@router.post("/", response_model=ApplicantOut)
def upsert_applicant(
    payload: ApplicantCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 동일 user_id의 가장 최근 1건을 업데이트, 없으면 생성
    obj = (
        db.query(Applicant)
        .filter(Applicant.user_id == current_user.id)
        .order_by(Applicant.applicant_id.desc())
        .first()
    )
    if obj is None:
        obj = Applicant(user_id=current_user.id)

    # 필수
    obj.last_name_en   = payload.last_name_en
    obj.first_name_en  = payload.first_name_en
    obj.birth_date     = payload.birth_date
    obj.gender         = payload.gender if isinstance(payload.gender, str) else str(payload.gender)
    obj.nationality    = payload.nationality

    # 선택
    obj.desired_industry          = _clean_str_or_none(payload.desired_industry)
    obj.education_level           = _clean_str_or_none(payload.education_level)
    obj.has_korean_certificate    = _clean_str_or_none(payload.has_korean_certificate)
    obj.korean_certificate_score  = _clean_str_or_none(payload.korean_certificate_score)
    obj.korean_certificate_type   = _clean_str_or_none(payload.korean_certificate_type)
    obj.korean_level              = _clean_str_or_none(payload.korean_level)
    obj.korean_speaking_level     = _clean_str_or_none(payload.korean_speaking_level)
    obj.visa_code                 = _clean_str_or_none(payload.visa_code)
    obj.visa_label                = _clean_str_or_none(payload.visa_label)
    obj.visa_status               = _clean_str_or_none(payload.visa_status)

    # JSONB 리스트(빈 문자열 제거)
    obj.visa_info = _clean_list_str(payload.visa_info)

    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@router.get("/", response_model=List[ApplicantOut])
def list_my_applicants(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Applicant)
        .filter(Applicant.user_id == current_user.id)
        .order_by(Applicant.applicant_id.desc())
        .all()
    )

@router.patch("/{applicant_id}/visa-info", response_model=ApplicantOut)
def append_visa_info(
    applicant_id: int,
    payload: VisaInfoAppend,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = (
        db.query(Applicant)
        .filter(Applicant.applicant_id == applicant_id, Applicant.user_id == current_user.id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Applicant not found")

    items = _clean_list_str(payload.items)
    if not items:
        return target

    from sqlalchemy import text
    from json import dumps
    stmt = text("""
        UPDATE applicants
           SET visa_info = COALESCE(visa_info, '[]'::jsonb) || :arr::jsonb
         WHERE applicant_id = :aid AND user_id = :uid
     RETURNING applicant_id, user_id, last_name_en, first_name_en, birth_date,
               gender, nationality,
               desired_industry, education_level,
               has_korean_certificate, korean_certificate_score, korean_certificate_type,
               korean_level, korean_speaking_level, visa_code, visa_label, visa_status,
               visa_info, created_at
    """)
    row = db.execute(
        stmt, {"arr": dumps(items), "aid": applicant_id, "uid": current_user.id}
    ).mappings().first()
    db.commit()
    if not row:
        raise HTTPException(status_code=500, detail="Failed to update visa_info")
    return row