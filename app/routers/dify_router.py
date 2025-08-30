import os
import random
import string
import json
import httpx
import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Depends
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.schemas.dify import AskRequest
from app.database import get_db
from app.models import models

router = APIRouter(prefix="/ai", tags=["AI"])

DIFY_API_KEY = os.getenv("DIFY_API_KEY")
DIFY_API_BASE = os.getenv("DIFY_API_BASE", "https://api.dify.ai/v1").rstrip("/")
DIFY_ENDPOINT = os.getenv("DIFY_ENDPOINT", "chat-messages")
ENV = os.getenv("ENV", "development")

CONNECT_TIMEOUT = float(os.getenv("DIFY_CONNECT_TIMEOUT", "10"))
READ_TIMEOUT    = float(os.getenv("DIFY_READ_TIMEOUT", "90"))
WRITE_TIMEOUT   = float(os.getenv("DIFY_WRITE_TIMEOUT", "15"))
POOL_TIMEOUT    = float(os.getenv("DIFY_POOL_TIMEOUT", "10"))

RETRY_MAX     = int(os.getenv("DIFY_RETRY_MAX", "2"))
RETRY_BACKOFF = float(os.getenv("DIFY_RETRY_BACKOFF", "1.5"))

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM  = os.getenv("JWT_ALGORITHM", "HS256")

if not DIFY_API_KEY:
    print("[AI] WARNING: DIFY_API_KEY is not set.")


def generate_user_id() -> str:
    letters = ''.join(random.choices(string.ascii_lowercase, k=3))
    numbers = ''.join(random.choices(string.digits, k=3))
    return f"{letters}-{numbers}"


def _get_current_user_id_from_cookie(request: Request, db: Session) -> int:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    scheme, _, credential = token.partition(" ")
    if scheme.lower() != "bearer" or not credential:
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")

    try:
        payload = jwt.decode(credential, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        google_sub = payload.get("sub")
        if not google_sub:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    user = db.query(models.User).filter(models.User.google_sub == google_sub).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user.id


def _extract_usage(data: dict) -> dict:
    """
    Dify 응답에서 usage 정보를 다양한 케이스로 추출.
    없으면 빈 dict 반환.
    """
    if not isinstance(data, dict):
        return {}
    # 1) 가장 흔한 케이스
    if isinstance(data.get("usage"), dict):
        return data["usage"]

    # 2) metadata.usage
    meta = data.get("metadata")
    if isinstance(meta, dict) and isinstance(meta.get("usage"), dict):
        return meta["usage"]

    # 3) token_usage 같은 변형 키
    for key in ("token_usage", "usage_info", "usage_stats"):
        if isinstance(data.get(key), dict):
            return data[key]

    # 4) messages 배열 안쪽 객체에 usage가 있는 케이스(드뭄)
    msgs = data.get("messages") or data.get("outputs")
    if isinstance(msgs, list):
        for m in msgs:
            if isinstance(m, dict) and isinstance(m.get("usage"), dict):
                return m["usage"]

    return {}  # 못 찾으면 빈 객체로


@router.post("/ask")
async def dify_ask(
    payload: AskRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    if not DIFY_API_KEY:
        raise HTTPException(status_code=500, detail="DIFY_API_KEY is not configured")

    user_id = _get_current_user_id_from_cookie(request, db)

    url = f"{DIFY_API_BASE}/{DIFY_ENDPOINT}"
    req_body = {
        "inputs": payload.inputs or {},
        "query": payload.query,
        "response_mode": payload.response_mode or "blocking",
        "user": payload.user or generate_user_id(),
    }
    if payload.conversation_id:
        req_body["conversation_id"] = payload.conversation_id
    if payload.files:
        req_body["files"] = payload.files

    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT,
        read=READ_TIMEOUT,
        write=WRITE_TIMEOUT,
        pool=POOL_TIMEOUT,
    )
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }

    attempt = 0
    last_error = None
    while attempt <= RETRY_MAX:
        try:
            async with httpx.AsyncClient(timeout=timeout, http2=True, headers=headers) as client:
                resp = await client.post(url, json=req_body)
                content_type = resp.headers.get("content-type", "")
                data = resp.json() if content_type.startswith("application/json") else {"raw_text": await resp.aread()}

                if resp.status_code >= 400:
                    if ENV != "production":
                        print("[AI][ERROR]", resp.status_code, data)
                        print("[AI][REQ]", url, json.dumps(req_body, ensure_ascii=False))
                    msg = data.get("message") if isinstance(data, dict) else str(data)
                    raise HTTPException(status_code=resp.status_code, detail=f"Dify error: {msg}")

                # ---- 정규화 ----
                answer = ""
                if isinstance(data, dict):
                    answer = data.get("answer") or ""
                    if not answer and isinstance(data.get("outputs"), list):
                        try:
                            answer = " ".join([str(o.get("text", "")) for o in data["outputs"]])
                        except Exception:
                            pass

                usage_obj = _extract_usage(data)  # ✅ 다양한 위치에서 usage 추출 (dict)

                # ---- DB 저장 ----
                try:
                    log = models.AiLog(user_id=user_id, answer=answer or "", usage=usage_obj or None)
                    db.add(log)
                    db.commit()
                    db.refresh(log)  # PK/created_at 채워오기
                except Exception as e:
                    db.rollback()
                    if ENV != "production":
                        print("[AI][LOG][ERROR]", repr(e))
                    raise HTTPException(status_code=500, detail="Failed to save AI log")

                # ---- 저장된 값만 반환 ----
                # PK 컬럼명이 log_id 또는 id 둘 중 무엇이든 대응
                log_pk = getattr(log, "log_id", None)
                if log_pk is None:
                    log_pk = getattr(log, "id", None)

                return {
                    "log_id": log_pk,
                    "user_id": log.user_id,
                    "answer": log.answer,
                    "usage": log.usage or {},
                    "created_at": (
                        log.created_at.isoformat() if isinstance(log.created_at, datetime) else str(log.created_at)
                    ),
                }

        except httpx.TimeoutException as e:
            last_error = e
            if ENV != "production":
                print(f"[AI][TIMEOUT] attempt={attempt} err={repr(e)}")
                print("[AI][REQ]", url, json.dumps(req_body, ensure_ascii=False))
        except httpx.RequestError as e:
            last_error = e
            if ENV != "production":
                print(f"[AI][NETWORK] attempt={attempt} err={repr(e)}")

        attempt += 1
        if attempt <= RETRY_MAX:
            await asyncio.sleep(RETRY_BACKOFF * attempt)

    if isinstance(last_error, httpx.TimeoutException):
        raise HTTPException(status_code=504, detail="Dify request timed out")
    raise HTTPException(status_code=502, detail=f"Network error: {last_error}")