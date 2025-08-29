import os
from datetime import timedelta, datetime
import traceback

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from httpx_oauth.clients.google import GoogleOAuth2
import httpx  # httpx 예외 처리를 위해 import 합니다.

# app/dependencies/auth.py에서 의존성을 가져옵니다.
from app.dependencies.auth import get_user_crud, UserCRUD
# app/schemas/user.py에서 Pydantic 스키마를 직접 가져옵니다.
from app.schemas.user import UserSchema, UserCreate

# --- 라우터 설정 ---
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

# --- 환경 변수 및 설정 ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))

REDIRECT_URI = "http://www.visalinkr.kro.kr:7770/auth/callback"

google_client = GoogleOAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)

# --- 유틸리티 함수 ---
def create_access_token(data: dict):
    """ 우리 서비스의 JWT 액세스 토큰을 생성합니다. """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

# --- API 엔드포인트 ---
@router.get("/login/google")
async def login_google():
    """ Google 로그인 페이지로 리디렉션합니다. """
    authorization_url = await google_client.get_authorization_url(
        REDIRECT_URI,
        # 'openid' 스코프를 추가해야 id_token이 정상적으로 반환됩니다.
        scope=["openid", "email", "profile"],
        extras_params={"access_type": "offline"},
    )
    return RedirectResponse(authorization_url)

@router.get("/callback")
async def auth_callback(request: Request, user_crud: UserCRUD = Depends(get_user_crud)):
    print(f"[AUTH] callback url = {request.url}")
    try:
        code = request.query_params.get("code")
        if not code:
            print("[AUTH] missing code")
            return RedirectResponse(url="/")

        # 1) code -> token
        try:
            token_data = await google_client.get_access_token(code, REDIRECT_URI)
            print(f"[AUTH] token_data keys = {list(token_data.keys())}")
        except httpx.HTTPStatusError as e:
            print(f"[AUTH][HTTP] token exchange error: {e.response.status_code} {e.response.text}")
            return RedirectResponse(url="/")

        access_token_from_google = token_data.get("access_token")
        if not access_token_from_google:
            print(f"[AUTH] no access_token in token_data: {token_data}")
            return RedirectResponse(url="/")

        # 2) userinfo
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    "https://openidconnect.googleapis.com/v1/userinfo",
                    headers={"Authorization": f"Bearer {access_token_from_google}"}
                )
                print(f"[AUTH] userinfo status = {r.status_code}")
                r.raise_for_status()
                userinfo = r.json()
            print(f"[AUTH] userinfo keys = {list(userinfo.keys())}")
        except httpx.HTTPStatusError as e:
            print(f"[AUTH][HTTP] userinfo error: {e.response.status_code} {e.response.text}")
            return RedirectResponse(url="/")

        google_sub = userinfo.get("sub")
        if not google_sub:
            print(f"[AUTH] userinfo missing 'sub': {userinfo}")
            return RedirectResponse(url="/")

        # 3) DB
        try:
            db_user = user_crud.get_by_google_sub(google_sub=google_sub)
            if not db_user:
                user_create = UserCreate(
                    google_sub=google_sub,
                    email=userinfo.get("email"),
                    name=userinfo.get("name"),
                    picture=userinfo.get("picture"),
                )
                db_user = user_crud.create(user=user_create)
        except Exception as db_e:
            print("[AUTH][DB] Exception:", repr(db_e))
            print(traceback.format_exc())
            return RedirectResponse(url="/")

        # 4) JWT
        try:
            # env 점검 로그 (가끔 비어있음)
            print(f"[AUTH][JWT] alg={JWT_ALGORITHM} | secret_set={bool(JWT_SECRET_KEY)}")
            access_token = create_access_token(data={"sub": db_user.google_sub})
        except Exception as jwt_e:
            print("[AUTH][JWT] create_access_token failed:", repr(jwt_e))
            print(traceback.format_exc())
            return RedirectResponse(url="/")

        # 5) Cookie
        response = RedirectResponse(url="/")
        response.set_cookie(
            key="access_token",
            value=f"Bearer {access_token}",
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite=os.getenv("COOKIE_SAMESITE", "lax"),
            secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        )
        return response

    except Exception as e:
        print("[AUTH][UNHANDLED]", repr(e))
        print(traceback.format_exc())
        # 개발 중이면 500 유지
        raise HTTPException(status_code=500, detail="인증 처리 중 오류가 발생했습니다.")

@router.get("/users/me", response_model=UserSchema)
async def read_users_me(request: Request, user_crud: UserCRUD = Depends(get_user_crud)):
    """ 인증된 사용자의 정보를 반환합니다. """
    token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        scheme, _, credential = token.partition(' ')
        if scheme.lower() != 'bearer':
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
        
        payload = jwt.decode(credential, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        google_sub: str = payload.get("sub")
        if google_sub is None:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    
    user = user_crud.get_by_google_sub(google_sub=google_sub)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.post("/logout")
@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/")
    resp.delete_cookie(
        key="access_token",
        samesite=os.getenv("COOKIE_SAMESITE", "lax"),
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    )
    return resp