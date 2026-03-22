from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import base64
import os
from typing import List, Optional
from database import (init_db, save_scan_session, get_sessions, get_session_detail,
                      compare_sessions, append_scan_to_session, replace_rack_in_session,
                      create_empty_session)
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


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    with open("static/dashboard.html", "r", encoding="utf-8") as f:
        return f.read()


async def read_images(files: List[UploadFile]) -> list:
    images = []
    for f in files:
        data = await f.read()
        b64 = base64.b64encode(data).decode("utf-8")
        images.append({
            "filename": f.filename,
            "b64": b64,
            "content_type": f.content_type or "image/jpeg"
        })
    return images


# ── 모드 1: 한 번에 업로드 (기존 방식) ──
@app.post("/api/scan")
async def upload_scan(
    store: str = Form(...),
    files: List[UploadFile] = File(...)
):
    if not files:
        raise HTTPException(status_code=400, detail="파일이 없습니다")
    images = await read_images(files)
    racks = await analyze_images_batch(images)
    session_id = save_scan_session(store, racks)
    diff = compare_sessions(store, session_id)
    return JSONResponse({"session_id": session_id, "store": store, "racks": racks, "diff": diff})


# ── 모드 2: 새 세션 시작 (이어서 업로드용) ──
@app.post("/api/scan/start")
async def start_session(store: str = Form(...)):
    session_id = create_empty_session(store)
    return JSONResponse({"session_id": session_id, "store": store, "message": "세션 시작됨"})


# ── 모드 2: 이어서 업로드 ──
@app.post("/api/scan/append/{session_id}")
async def append_scan(
    session_id: int,
    files: List[UploadFile] = File(...)
):
    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="세션 없음")
    if not files:
        raise HTTPException(status_code=400, detail="파일이 없습니다")

    images = await read_images(files)
    # 기존 랙 번호 이어서 시작
    existing_rack_count = len(detail["racks"])
    racks = await analyze_images_batch(images, start_rack_num=existing_rack_count + 1)
    append_scan_to_session(session_id, racks)

    updated = get_session_detail(session_id)
    return JSONResponse({
        "session_id": session_id,
        "added_racks": len(racks),
        "total_racks": len(updated["racks"]),
        "total_products": sum(len(r["products"]) for r in updated["racks"]),
        "racks": racks
    })


# ── 모드 2: 세션 완료 ──
@app.post("/api/scan/finish/{session_id}")
async def finish_session(session_id: int):
    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="세션 없음")
    diff = compare_sessions(detail["store"], session_id)
    return JSONResponse({
        "session_id": session_id,
        "store": detail["store"],
        "total_racks": len(detail["racks"]),
        "total_products": sum(len(r["products"]) for r in detail["racks"]),
        "diff": diff
    })


# ── 모드 3: 랙별 업로드 (특정 랙 교체) ──
@app.post("/api/scan/rack/{session_id}")
async def upload_rack(
    session_id: int,
    rack_number: int = Form(...),
    files: List[UploadFile] = File(...)
):
    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="세션 없음")
    if not files:
        raise HTTPException(status_code=400, detail="파일이 없습니다")

    images = await read_images(files)
    racks = await analyze_images_batch(images, start_rack_num=rack_number, single_rack=True)

    # 해당 랙 번호만 교체
    products = racks[0]["products"] if racks else []
    replace_rack_in_session(session_id, rack_number, products)

    updated = get_session_detail(session_id)
    return JSONResponse({
        "session_id": session_id,
        "rack_number": rack_number,
        "products_count": len(products),
        "total_products": sum(len(r["products"]) for r in updated["racks"]),
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
    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="세션 없음")
    return compare_sessions(detail["store"], session_id)
