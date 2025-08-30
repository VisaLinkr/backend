# app/schemas/applicant.py
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List, Literal

# ✅ 프론트에서 기본 인적사항 + 확장 필드까지 저장(업서트)할 때 쓰는 입력 모델
#    - 기존 ApplicantCreate를 확장 (기존 필드 유지 + 선택 필드 추가)
class ApplicantCreate(BaseModel):
    # --- 기존 필수 필드 ---
    last_name_en: str
    first_name_en: str
    birth_date: date

    # gender 한 글자(M/F)만 강제하던 것 → 완화
    # 필요하다면 Literal로 제한하거나, 자유 텍스트(예: "male", "female")도 허용
    gender: Literal["M", "F", "male", "female"] = Field(..., description="성별: M/F 또는 male/female")
    nationality: str

    # ✅ 확장 필드들(모두 선택)
    desired_industry: Optional[str] = None
    education_level: Optional[str] = None
    has_korean_certificate: Optional[str] = None   # 'yes' / 'no' 등 문자열 그대로
    korean_certificate_score: Optional[str] = None
    korean_certificate_type: Optional[str] = None
    korean_level: Optional[str] = None
    korean_speaking_level: Optional[str] = None
    visa_code: Optional[str] = None
    visa_label: Optional[str] = None
    visa_status: Optional[str] = None

    # 가변 기본값은 반드시 default_factory 사용!
    visa_info: List[str] = Field(default_factory=list, description="비자 정보 문자열 리스트")


# ✅ DB에서 꺼내서 프론트로 반환할 때 쓰는 출력 모델
class ApplicantOut(BaseModel):
    applicant_id: int
    user_id: Optional[int] = None

    last_name_en: str
    first_name_en: str
    birth_date: date
    gender: str
    nationality: str

    # 확장 필드(선택)
    desired_industry: Optional[str] = None
    education_level: Optional[str] = None
    has_korean_certificate: Optional[str] = None
    korean_certificate_score: Optional[str] = None
    korean_certificate_type: Optional[str] = None
    korean_level: Optional[str] = None
    korean_speaking_level: Optional[str] = None
    visa_code: Optional[str] = None
    visa_label: Optional[str] = None
    visa_status: Optional[str] = None

    visa_info: List[str] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True  # SQLAlchemy 모델 -> Pydantic 변환 허용


# ✅ 비자 문자열 항목들을 목록으로 추가할 때 쓰는 간단한 스키마
class VisaInfoAppend(BaseModel):
    items: List[str] = Field(default_factory=list)