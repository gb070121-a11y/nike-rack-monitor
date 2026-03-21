from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import base64
import os
from typing import List
from database import init_db, save_scan_session, get_sessions, get_session_detail, compare_sessions
from analyzer import analyze_images_batch

app = FastAPI(title="Nike Rack Monitor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/scan")
async def upload_scan(
    store: str = Form(...),
    files: List[UploadFile] = File(...)
):
    """사진 묶음 업로드 → 분석 → 저장"""
    if not files:
        raise HTTPException(status_code=400, detail="파일이 없습니다")

    # 모든 파일을 메모리로 읽기
    images = []
    for f in files:
        data = await f.read()
        b64 = base64.b64encode(data).decode("utf-8")
        images.append({
            "filename": f.filename,
            "b64": b64,
            "content_type": f.content_type or "image/jpeg"
        })

    # GPT-4o 병렬 분석
    racks = await analyze_images_batch(images)

    # DB 저장
    session_id = save_scan_session(store, racks)

    # 이전 회차와 비교
    diff = compare_sessions(store, session_id)

    return JSONResponse({
        "session_id": session_id,
        "store": store,
        "racks": racks,
        "diff": diff
    })


@app.get("/api/sessions")
async def list_sessions(store: str = None):
    return get_sessions(store)


@app.get("/api/sessions/{session_id}")
async def session_detail(session_id: int):
    data = get_session_detail(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="세션 없음")
    return data


@app.get("/api/compare/{session_id_a}/{session_id_b}")
async def compare_two(session_id_a: int, session_id_b: int):
    return compare_sessions(None, session_id_b, session_id_a)


@app.get("/api/compare-latest/{session_id}")
async def compare_latest(session_id: int):
    """세션을 같은 매장의 직전 세션과 자동 비교"""
    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="세션 없음")
    return compare_sessions(detail["store"], session_id)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    with open("static/dashboard.html", "r", encoding="utf-8") as f:
        return f.read()
