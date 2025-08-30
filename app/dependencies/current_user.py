# app/dependencies/current_user.py
import os
from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import models  # models.User 가정 (app/models/models.py 에 User 존재)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    scheme, _, credential = token.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")

    try:
        payload = jwt.decode(credential, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        google_sub = payload.get("sub")
        if not google_sub:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(models.User).filter(models.User.google_sub == google_sub).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user