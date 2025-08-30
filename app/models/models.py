from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, String, DateTime, func
from datetime import datetime, timedelta, timezone
from app.database import Base # database.py에서 Base를 가져옵니다.
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

KST = timezone(timedelta(hours=9))

class Province(Base):
    __tablename__ = "provinces"

    province_id = Column(Integer, primary_key=True, index=True)
    province_name = Column(String, nullable=False, unique=True, index=True)

    districts = relationship("District", back_populates="province", lazy="selectin")


class District(Base):
    __tablename__ = "districts"

    district_id = Column(Integer, primary_key=True, index=True)
    district_name = Column(String, nullable=False, index=True)

    province_id = Column(Integer, ForeignKey("provinces.province_id", ondelete="RESTRICT"), nullable=False, index=True)

    # 숫자 컬럼(인구, 급여, 외국인 등록 수)
    population = Column(Integer, nullable=True)  # CSV에 따라 NULL 가능
    avg_monthly_salary = Column(Integer, nullable=True)
    registered_foreigners = Column(Integer, nullable=True)

    # JSONB 배열: ["정보통신업","제조업", ...]
    major_industries = Column(JSONB, nullable=True)
    data_updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(KST))

    # 관계
    province = relationship("Province", back_populates="districts")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    google_sub = Column(String(255), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    picture = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(KST))