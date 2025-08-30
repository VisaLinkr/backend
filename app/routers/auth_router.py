# app/routers/auth_router.py
import os
from datetime import timedelta, datetime
import traceback

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from httpx_oauth.clients.google import GoogleOAuth2
import httpx

from app.dependencies.auth import get_user_crud, UserCRUD
from app.schemas.user import UserSchema, UserCreate

router = APIRouter(prefix="/auth", tags=["Authentication"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))

google_client = GoogleOAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def cookie_kwargs_for(request: Request) -> dict:
    """
    요청 스킴/오리진에 맞게 쿠키 속성을 자동 설정
    - HTTP 단일 오리진:   Secure=False, SameSite=Lax, domain=None
    - HTTPS 단일 오리진:  Secure=True,  SameSite=Lax, domain=None
    (여러 서브도메인에서 공유해야 하면 domain을 ".example.com"으로 조정)
    """
    is_https = request.url.scheme == "https"
    return {
        "httponly": True,
        "max_age": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "secure": is_https,
        "samesite": "lax",
        "domain": None,   # 필요 시 ".visalinkr.kro.kr" 등으로 변경
        "path": "/",
    }


def frontend_url_for(request: Request) -> str:
    """
    프론트는 같은 오리진에서 서빙하므로 루트로 돌려보내면 충분.
    (프론트를 따로 돌리는 구조라면 여기서 오리진을 구성해 반환)
    """
    return "/"


@router.get("/login/google")
async def login_google(request: Request):
    """
    구글 로그인 시작: redirect_uri를 매 요청 기준으로 동적 생성
    """
    redirect_uri = str(request.url_for("google_callback"))
    authorization_url = await google_client.get_authorization_url(
        redirect_uri,
        scope=["openid", "email", "profile"],
        extras_params={"access_type": "offline"},
    )
    return RedirectResponse(authorization_url)


@router.get("/callback", name="google_callback")
async def auth_callback(request: Request, user_crud: UserCRUD = Depends(get_user_crud)):
    print(f"[AUTH] callback url = {request.url}")

    try:
        code = request.query_params.get("code")
        if not code:
            return RedirectResponse(url=frontend_url_for(request))

        # 1) code -> token (동일 redirect_uri 사용)
        redirect_uri = str(request.url_for("google_callback"))
        try:
            token_data = await google_client.get_access_token(code, redirect_uri)
        except httpx.HTTPStatusError as e:
            print(f"[AUTH][HTTP] token exchange error: {e.response.status_code} {e.response.text}")
            return RedirectResponse(url=frontend_url_for(request))

        access_token_from_google = token_data.get("access_token")
        if not access_token_from_google:
            return RedirectResponse(url=frontend_url_for(request))

        # 2) userinfo
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    "https://openidconnect.googleapis.com/v1/userinfo",
                    headers={"Authorization": f"Bearer {access_token_from_google}"}
                )
                r.raise_for_status()
                userinfo = r.json()
        except httpx.HTTPStatusError as e:
            print(f"[AUTH][HTTP] userinfo error: {e.response.status_code} {e.response.text}")
            return RedirectResponse(url=frontend_url_for(request))

        google_sub = userinfo.get("sub")
        if not google_sub:
            return RedirectResponse(url=frontend_url_for(request))

        # 3) DB 저장/조회
        db_user = user_crud.get_by_google_sub(google_sub=google_sub)
        if not db_user:
            user_create = UserCreate(
                google_sub=google_sub,
                email=userinfo.get("email"),
                name=userinfo.get("name"),
                picture=userinfo.get("picture"),
            )
            db_user = user_crud.create(user=user_create)

        # 4) JWT 생성
        access_token = create_access_token(data={"sub": db_user.google_sub})

        # 5) 쿠키 발급 + 프론트로 리다이렉트
        response = RedirectResponse(url=frontend_url_for(request))
        response.set_cookie(
            key="access_token",
            value=f"Bearer {access_token}",
            **cookie_kwargs_for(request),
        )
        return response

    except Exception as e:
        print("[AUTH][UNHANDLED]", repr(e))
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="인증 처리 중 오류가 발생했습니다.")


@router.get("/users/me", response_model=UserSchema)
async def read_users_me(request: Request, user_crud: UserCRUD = Depends(get_user_crud)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        scheme, _, credential = token.partition(" ")
        if scheme.lower() != "bearer":
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
async def logout(request: Request):
    resp = RedirectResponse(url=frontend_url_for(request))
    # 삭제 시에도 동일 속성으로 지정해야 정확히 지워짐
    ck = cookie_kwargs_for(request)
    resp.delete_cookie(
        key="access_token",
        samesite=ck["samesite"],
        secure=ck["secure"],
        domain=ck["domain"],
        path=ck["path"],
    )
    return resp