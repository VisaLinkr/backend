from sqlalchemy.orm import Session
from fastapi import Depends

# 절대 경로를 사용하도록 import 구문을 수정합니다.
from app.models import models
from app.database import get_db
from app.schemas.user import UserCreate

class UserCRUD:
    """
    User 모델에 대한 CRUD 작업을 처리하는 클래스.
    DB 세션에 의존합니다.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_by_google_sub(self, google_sub: str):
        """ Google 'sub' ID로 사용자를 조회합니다. """
        return self.db.query(models.User).filter(models.User.google_sub == google_sub).first()

    def create(self, user: UserCreate):
        """ 새로운 사용자를 생성합니다. """
        db_user = models.User(
            google_sub=user.google_sub,
            email=user.email,
            name=user.name,
            picture=user.picture
        )
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

def get_user_crud(db: Session = Depends(get_db)) -> UserCRUD:
    """
    UserCRUD 클래스의 인스턴스를 생성하여 반환하는 의존성 함수.
    """
    return UserCRUD(db=db)

