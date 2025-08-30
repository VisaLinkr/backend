from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List

class ApplicantCreate(BaseModel):
    last_name_en: str
    first_name_en: str
    birth_date: date
    gender: str = Field(min_length=1, max_length=1)   # 앱 레벨에서 최소 검증
    nationality: str
    residence_region: str
    visa_info: List[str] = []                         # 선택 입력

class ApplicantOut(BaseModel):
    applicant_id: int
    user_id: Optional[int] = None
    last_name_en: str
    first_name_en: str
    birth_date: date
    gender: str
    nationality: str
    residence_region: str
    visa_info: List[str]
    created_at: datetime

    class Config:
        from_attributes = True  # SQLAlchemy 모델 -> Pydantic 변환
        
class VisaInfoAppend(BaseModel):
    items: List[str] = []