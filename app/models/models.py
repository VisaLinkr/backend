from sqlalchemy import TIMESTAMP, Column, Integer, String, DateTime
from datetime import datetime, timedelta, timezone
from app.database import Base # database.py에서 Base를 가져옵니다.

KST = timezone(timedelta(hours=9))

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    google_sub = Column(String(255), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    picture = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(KST))