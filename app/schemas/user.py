from pydantic import BaseModel
from typing import Optional # Optional을 import 해야 합니다.
from datetime import datetime

# --- User 스키마 ---

class UserBase(BaseModel):
    """ 모든 User 스키마가 공통으로 가지는 필드 """
    email: str
    # 파이썬 3.9 호환성을 위해 `str | None` 대신 `Optional[str]`을 사용합니다.
    name: Optional[str] = None
    picture: Optional[str] = None

class UserCreate(UserBase):
    """ 사용자 생성을 위한 스키마 """
    google_sub: str

class UserSchema(UserBase):
    """ API 응답(조회)에 사용될 스키마 """
    id: int
    google_sub: str
    created_at: datetime

    class Config:
        from_attributes = True # SQLAlchemy 모델을 Pydantic 모델로 변환
