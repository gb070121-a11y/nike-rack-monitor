from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import base64
import io
import os
from typing import List, Optional
from database import (init_db, save_scan_session, get_sessions, get_session_detail,
                      compare_sessions, append_scan_to_session, replace_rack_in_session,
                      create_empty_session, finish_session, delete_session, delete_products,
                      move_products_to_rack, get_client)
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

@app.get("/manage", response_class=HTMLResponse)
async def manage():
    with open("static/manage.html", "r", encoding="utf-8") as f:
        return f.read()

async def read_images(files: List[UploadFile]) -> list:
    images = []
    for f in files:
        data = await f.read()
        b64 = base64.b64encode(data).decode("utf-8")
        images.append({"filename": f.filename, "b64": b64, "content_type": f.content_type or "image/jpeg"})
    return images

def build_racks_from_map(images, rack_map, offset=0):
    rack_dict = {}
    for img, rack_num in zip(images, rack_map):
        actual = rack_num + offset
        if actual not in rack_dict:
            rack_dict[actual] = []
        rack_dict[actual].append(img)
    return rack_dict

async def analyze_rack_dict(rack_dict):
    all_racks = []
    tasks = {}
    for rack_num, imgs in rack_dict.items():
        tasks[rack_num] = analyze_images_batch(imgs, start_rack_num=rack_num, single_rack=True)
    results = await asyncio.gather(*tasks.values())
    for rack_num, racks in zip(tasks.keys(), results):
        products = []
        for r in racks:
            products.extend(r["products"])
        all_racks.append({"rack_number": rack_num, "products": products, "photo_count": len(rack_dict[rack_num])})
    return sorted(all_racks, key=lambda x: x["rack_number"])


# ── 한번에 + 랙맵 ──
@app.post("/api/scan/with-racks")
async def upload_scan_with_racks(
    store: str = Form(...),
    files: List[UploadFile] = File(...),
    rack_map: List[int] = Form(...)
):
    images = await read_images(files)
    rack_dict = build_racks_from_map(images, rack_map)
    all_racks = await analyze_rack_dict(rack_dict)
    session_id = save_scan_session(store, all_racks)
    diff = compare_sessions(store, session_id)
    return JSONResponse({"session_id": session_id, "store": store,
                         "rack_count": len(all_racks),
                         "product_count": sum(len(r["products"]) for r in all_racks), "diff": diff})


# ── 세션 시작 ──
@app.post("/api/scan/start")
async def start_session(store: str = Form(...)):
    session_id = create_empty_session(store)
    return JSONResponse({"session_id": session_id, "store": store})


# ── 이어서 + 랙맵 ──
@app.post("/api/scan/append-with-racks/{session_id}")
async def append_scan_with_racks(
    session_id: int,
    files: List[UploadFile] = File(...),
    rack_map: List[int] = Form(...)
):
    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="세션 없음")
    images = await read_images(files)
    offset = len(detail["racks"])
    rack_dict = build_racks_from_map(images, rack_map, offset)
    all_racks = await analyze_rack_dict(rack_dict)
    append_scan_to_session(session_id, all_racks)
    updated = get_session_detail(session_id)
    return JSONResponse({"session_id": session_id, "added_racks": len(all_racks),
                         "total_racks": len(updated["racks"]),
                         "total_products": sum(len(r["products"]) for r in updated["racks"])})


# ── 세션 완료 ──
@app.post("/api/scan/finish/{session_id}")
async def finish_session_api(session_id: int):
    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="세션 없음")
    finish_session(session_id)
    diff = compare_sessions(detail["store"], session_id)
    return JSONResponse({"session_id": session_id, "store": detail["store"],
                         "total_racks": len(detail["racks"]),
                         "total_products": sum(len(r["products"]) for r in detail["racks"]),
                         "diff": diff})


# ── 랙별 교체 ──
@app.post("/api/scan/rack/{session_id}")
async def upload_rack(
    session_id: int,
    rack_number: int = Form(...),
    files: List[UploadFile] = File(...)
):
    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="세션 없음")
    images = await read_images(files)
    racks = await analyze_images_batch(images, start_rack_num=rack_number, single_rack=True)
    products = racks[0]["products"] if racks else []
    replace_rack_in_session(session_id, rack_number, products)
    updated = get_session_detail(session_id)
    return JSONResponse({"session_id": session_id, "rack_number": rack_number,
                         "products_count": len(products),
                         "total_products": sum(len(r["products"]) for r in updated["racks"])})


# ── 기존 한번에 (하위 호환) ──
@app.post("/api/scan")
async def upload_scan(store: str = Form(...), files: List[UploadFile] = File(...)):
    images = await read_images(files)
    racks = await analyze_images_batch(images)
    session_id = save_scan_session(store, racks)
    diff = compare_sessions(store, session_id)
    return JSONResponse({"session_id": session_id, "store": store, "racks": racks, "diff": diff})


# ── 세션 목록 / 상세 ──
@app.get("/api/sessions")
async def list_sessions(store: str = None):
    return get_sessions(store)

@app.get("/api/sessions/{session_id}")
async def session_detail(session_id: int):
    data = get_session_detail(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="세션 없음")
    return data


# ── 비교 ──
@app.get("/api/compare/{session_id_a}/{session_id_b}")
async def compare_two(session_id_a: int, session_id_b: int):
    return compare_sessions(None, session_id_b, session_id_a)

@app.get("/api/compare-latest/{session_id}")
async def compare_latest(session_id: int):
    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="세션 없음")
    return compare_sessions(detail["store"], session_id)


# ── 데이터 관리: 세션 삭제 ──
@app.delete("/api/sessions/{session_id}")
async def delete_session_api(session_id: int):
    delete_session(session_id)
    return JSONResponse({"success": True})


# ── 데이터 관리: 제품 삭제 ──
@app.delete("/api/products")
async def delete_products_api(product_ids: List[int] = Form(...)):
    delete_products(product_ids)
    return JSONResponse({"success": True, "deleted": len(product_ids)})


# ── 데이터 관리: 랙 이동 ──
@app.post("/api/products/move-rack")
async def move_rack_api(
    product_ids: List[int] = Form(...),
    target_rack: int = Form(...),
    session_id: int = Form(...)
):
    move_products_to_rack(product_ids, target_rack, session_id)
    return JSONResponse({"success": True})


# ── 엑셀 다운로드 ──
@app.get("/api/sessions/{session_id}/excel")
async def download_excel(session_id: int, type: str = "all"):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl 미설치")

    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="세션 없음")

    diff = compare_sessions(detail["store"], session_id)

    wb = openpyxl.Workbook()

    # 헤더 스타일
    def style_header(ws, headers, fills):
        for col, (h, fill) in enumerate(zip(headers, fills), 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=fill)
            cell.alignment = Alignment(horizontal="center")

    STORE_LABELS = {"gimhae": "김해", "jeonggwan": "정관"}
    store_name = STORE_LABELS.get(detail["store"], detail["store"])

    # 시트1: 전체 현황
    ws1 = wb.active
    ws1.title = "전체현황"
    headers1 = ["랙번호", "품번", "제품명", "정가", "할인가", "할인율"]
    fills1 = ["FF4D00", "FF4D00", "FF4D00", "FF4D00", "FF4D00", "FF4D00"]
    style_header(ws1, headers1, fills1)
    for rack in detail["racks"]:
        for p in rack["products"]:
            ws1.append([rack["rack_number"], p.get("sku",""), p.get("name",""),
                        p.get("price",""), p.get("sale_price",""),
                        f"{p['discount_rate']}%" if p.get("discount_rate") else ""])

    # 시트2: 신규 추가
    ws2 = wb.create_sheet("신규추가")
    headers2 = ["랙번호", "품번", "제품명", "정가", "할인가", "할인율"]
    fills2 = ["39D353", "39D353", "39D353", "39D353", "39D353", "39D353"]
    style_header(ws2, headers2, fills2)
    if diff.get("has_previous"):
        for c in diff["changes"]:
            if c["type"] == "added":
                ws2.append([c["rack"], c["sku"], c.get("name",""),
                            c.get("new_price",""), c.get("new_sale_price",""),
                            f"{c['new_discount']}%" if c.get("new_discount") else ""])

    # 시트3: 사라진 품번
    ws3 = wb.create_sheet("사라진품번")
    headers3 = ["랙번호", "품번", "제품명", "이전정가", "이전할인가", "이전할인율"]
    fills3 = ["F85149", "F85149", "F85149", "F85149", "F85149", "F85149"]
    style_header(ws3, headers3, fills3)
    if diff.get("has_previous"):
        for c in diff["changes"]:
            if c["type"] == "removed":
                ws3.append([c["rack"], c["sku"], c.get("name",""),
                            c.get("old_price",""), c.get("old_sale_price",""),
                            f"{c['old_discount']}%" if c.get("old_discount") else ""])

    # 시트4: 가격변동
    ws4 = wb.create_sheet("가격변동")
    headers4 = ["랙번호", "품번", "제품명", "변동항목", "이전값", "새값"]
    fills4 = ["E3B341", "E3B341", "E3B341", "E3B341", "E3B341", "E3B341"]
    style_header(ws4, headers4, fills4)
    if diff.get("has_previous"):
        field_labels = {"price": "정가", "sale_price": "할인가", "discount_rate": "할인율", "rack": "랙위치"}
        for c in diff["changes"]:
            if c["type"] == "changed":
                for ch in c["changes"]:
                    ws4.append([c["rack"], c["sku"], c.get("name",""),
                                field_labels.get(ch["field"], ch["field"]),
                                ch["old"], ch["new"]])

    # 열 너비 자동 조정
    for ws in [ws1, ws2, ws3, ws4]:
        for col in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=0)
            ws.column_dimensions[col[0].column_letter].width = max(12, max_len + 2)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"rack_{detail['store']}_{detail['scanned_at'][:10]}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
