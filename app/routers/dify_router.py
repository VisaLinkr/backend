# app/routers/dify_router.py
import os
import random
import string
import json
import httpx
import asyncio
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Depends
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import models  # User, Applicant, AiLog

router = APIRouter(prefix="/ai", tags=["AI"])

DIFY_API_KEY   = os.getenv("DIFY_API_KEY")
DIFY_API_BASE  = os.getenv("DIFY_API_BASE", "https://api.dify.ai/v1").rstrip("/")
DIFY_ENDPOINT  = os.getenv("DIFY_ENDPOINT", "chat-messages")
ENV            = os.getenv("ENV", "development")

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


def _gen_user_tag() -> str:
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


def _fmt_date(d: date) -> str:
    try:
        return d.strftime("%Y.%m.%d")
    except Exception:
        return str(d)


def _gender_ko(g: Optional[str]) -> str:
    if not g:
        return "미상"
    v = g.strip().lower()
    if v in ("m", "male"):
        return "남자"
    if v in ("f", "female"):
        return "여자"
    return g


def _yn_ko(v: Optional[str]) -> str:
    if v is None or v == "":
        return "미제출"
    v2 = str(v).strip().lower()
    return "있음" if v2 in ("y", "yes", "true", "1") else "없음"


def build_query_from_applicant(a: models.Applicant) -> str:
    parts = []
    parts.append(f"{a.last_name_en} {a.first_name_en}")
    parts.append(_gender_ko(a.gender))
    parts.append(f"국적 {a.nationality}")
    parts.append(f"생일 {_fmt_date(a.birth_date)}")
    if a.education_level:
        parts.append(f"학력 {a.education_level}")
    if a.has_korean_certificate is not None:
        parts.append(f"한국어능력시험 보유 {_yn_ko(a.has_korean_certificate)}")
    if a.korean_certificate_score:
        parts.append(f"점수 {a.korean_certificate_score}")
    if a.korean_certificate_type:
        parts.append(f"등급 {a.korean_certificate_type}")
    if a.korean_level:
        parts.append(f"한국어 사용 수준 {a.korean_level}")
    if a.korean_speaking_level:
        parts.append(f"한국어 구사 수준 {a.korean_speaking_level}")
    if a.desired_industry:
        parts.append(f"{a.desired_industry} 업무 희망")
    if a.visa_status:
        parts.append(f"현재 비자 상태 {a.visa_status}")
    if a.visa_code or a.visa_label:
        parts.append(f"비자 {(a.visa_code or '')} {(a.visa_label or '')}".strip())
    return ", ".join(parts)


def _extract_usage(data: dict) -> dict:
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("usage"), dict):
        return data["usage"]
    meta = data.get("metadata")
    if isinstance(meta, dict) and isinstance(meta.get("usage"), dict):
        return meta["usage"]
    for key in ("token_usage", "usage_info", "usage_stats"):
        if isinstance(data.get(key), dict):
            return data[key]
    msgs = data.get("messages") or data.get("outputs")
    if isinstance(msgs, list):
        for m in msgs:
            if isinstance(m, dict) and isinstance(m.get("usage"), dict):
                return m["usage"]
    return {}


async def _call_dify_and_log(db: Session, user_id: int, query: str) -> dict:
    if not DIFY_API_KEY:
        raise HTTPException(status_code=500, detail="DIFY_API_KEY is not configured")

    url = f"{DIFY_API_BASE}/{DIFY_ENDPOINT}"
    headers = {"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"}
    body = {
        "inputs": {},                 # 항상 빈 객체
        "query": query,
        "response_mode": "blocking",
        "user": _gen_user_tag(),
    }
    timeout = httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT, write=WRITE_TIMEOUT, pool=POOL_TIMEOUT)

    attempt = 0
    last_err = None
    while attempt <= RETRY_MAX:
        try:
            async with httpx.AsyncClient(timeout=timeout, http2=True, headers=headers) as client:
                resp = await client.post(url, json=body)
                ctype = resp.headers.get("content-type", "")
                data = resp.json() if ctype.startswith("application/json") else {"raw_text": await resp.aread()}

                if resp.status_code >= 400:
                    if ENV != "production":
                        print("[AI][ERROR]", resp.status_code, data)
                        print("[AI][REQ]", url, json.dumps(body, ensure_ascii=False))
                    msg = data.get("message") if isinstance(data, dict) else resp.text
                    raise HTTPException(status_code=resp.status_code, detail=f"Dify error: {msg}")

                answer = ""
                if isinstance(data, dict):
                    answer = data.get("answer") or ""
                    if not answer and isinstance(data.get("outputs"), list):
                        try:
                            answer = " ".join([str(o.get("text", "")) for o in data["outputs"]])
                        except Exception:
                            pass
                usage_obj = _extract_usage(data)

                # DB 저장
                log = models.AiLog(user_id=user_id, query=query, answer=answer or "", usage=usage_obj or None)
                try:
                    db.add(log)
                    db.commit()
                    db.refresh(log)
                except Exception as e:
                    db.rollback()
                    if ENV != "production":
                        print("[AI][LOG][ERROR]", repr(e))
                    raise HTTPException(status_code=500, detail="Failed to save AI log")

                # 저장된 값만 반환
                log_pk = getattr(log, "log_id", None) or getattr(log, "id", None)
                return {
                    "log_id": log_pk,
                    "user_id": log.user_id,
                    "query": log.query,
                    "answer": log.answer,
                    "usage": log.usage or {},
                    "created_at": log.created_at.isoformat()
                        if isinstance(log.created_at, datetime) else str(log.created_at),
                }

        except httpx.TimeoutException as e:
            last_err = e
            if ENV != "production":
                print(f"[AI][TIMEOUT] attempt={attempt} err={repr(e)}")
        except httpx.RequestError as e:
            last_err = e
            if ENV != "production":
                print(f"[AI][NETWORK] attempt={attempt} err={repr(e)}")

        attempt += 1
        if attempt <= RETRY_MAX:
            await asyncio.sleep(RETRY_BACKOFF * attempt)

    if isinstance(last_err, httpx.TimeoutException):
        raise HTTPException(status_code=504, detail="Dify request timed out")
    raise HTTPException(status_code=502, detail=f"Network error: {last_err}")


@router.post("/diagnose")
async def diagnose_with_saved_applicant(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    바디 없음. (유저당 Applicant 하나라는 가정)
    - 로그인 쿠키로 user_id 식별
    - 해당 user_id의 Applicant 1건을 로드
    - 질의문 생성 → Dify 호출/ai_logs 저장 → 저장된 값만 반환
    """
    user_id = _get_current_user_id_from_cookie(request, db)

    a = db.query(models.Applicant).filter(models.Applicant.user_id == user_id).order_by(
        models.Applicant.applicant_id.desc()
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="No applicant found for this user")

    query = build_query_from_applicant(a)
    return await _call_dify_and_log(db, user_id, query)