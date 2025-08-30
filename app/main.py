import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.routers import auth_router, province_router

app = FastAPI()

FRONTEND_DIR = os.getenv("FRONTEND_DIR", "/home/visalinkr/backend/out")

def mount_if_exists(url_path: str, subdir: str):
    path = os.path.join(FRONTEND_DIR, subdir)
    if os.path.isdir(path):
        app.mount(url_path, StaticFiles(directory=path), name=subdir)
        print(f"[FE] Mounted {url_path} -> {path}")
    else:
        print(f"[FE][WARN] Skip mount: {path} not found")

# 1) ✅ 먼저 인증/백엔드 라우터를 등록 ( /auth/* )
app.include_router(auth_router.router)
app.include_router(province_router.router)

# 2) 정적 폴더 마운트
mount_if_exists("/_next", "_next")
mount_if_exists("/assets", "assets")
mount_if_exists("/static", "static")

# 3) CORS (동일 오리진이면 사실 필요 없음)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://www.visalinkr.kro.kr:7770",   # 지금 7770에서 직접 서빙이면 포트 포함
        "http://www.visalinkr.kro.kr",        # Nginx로 80에서 서빙할 경우 대비
        "http://localhost:3000",              # 로컬 개발용
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4) ✅ SPA 폴백은 맨 마지막! ( /auth/* 를 덮지 않도록 )
@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>index.html not found</h1>", status_code=404)

@app.get("/{full_path:path}", response_class=HTMLResponse)
async def spa(full_path: str):
    # 요청 파일이 존재하면 그대로 제공
    candidate = os.path.join(FRONTEND_DIR, full_path)
    if os.path.isfile(candidate):
        return FileResponse(candidate)

    # 디렉토리 index.html
    index_html = os.path.join(candidate, "index.html")
    if os.path.isfile(index_html):
        return FileResponse(index_html)

    # 최종 폴백: 루트 index.html
    root_index = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.isfile(root_index):
        return FileResponse(root_index)

    return HTMLResponse("<h1>index.html not found</h1>", status_code=404)