from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# app/routers/auth_router.py 파일에서 'router' 객체를 가져와 'auth_router'라는 이름으로 사용합니다.
from app.routers.auth_router import router as auth_router

app = FastAPI()

# --- CORS 설정 ---
# 프론트엔드 개발 서버의 주소를 origins 목록에 추가합니다.
origins = [
    "http://localhost:5173",
    # 필요에 따라 다른 출처(도메인)를 추가할 수 있습니다.
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,       # 쿠키를 포함한 요청을 허용
    allow_methods=["*"],          # 모든 HTTP 메서드 허용
    allow_headers=["*"],          # 모든 HTTP 헤더 허용
)

# 'static' 폴더를 정적 파일 디렉터리로 마운트합니다.
app.mount("/static", StaticFiles(directory="static"), name="static")

# Jinja2 템플릿 설정
templates = Jinja2Templates(directory="static")

# 인증 라우터를 앱에 포함합니다.
app.include_router(auth_router)

# 루트 URL('/')에 대한 GET 요청을 처리하여 index.html을 렌더링합니다.
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})