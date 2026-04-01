from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import base64
import io
import os
from typing import List

from database import (
    init_db, save_rack_scan, get_store_overview,
    get_recent_changes, get_rack_history, search_sku,
    delete_rack, get_excel_data, RACK_MAP
)
from analyzer import analyze_images_batch

app = FastAPI(title="Nike Rack Monitor V2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── 페이지 라우트 ──
@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/floorplan", response_class=HTMLResponse)
async def floorplan():
    with open("static/floorplan.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    with open("static/dashboard.html", "r", encoding="utf-8") as f:
        return f.read()


# ── 이미지 읽기 헬퍼 ──
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


# ============================================================
# 스캔 API
# ============================================================

# ── 랙별 스캔 (평면도에서 클릭) ──
@app.post("/api/scan/rack")
async def scan_rack(
    store: str = Form(...),
    rack_name: str = Form(...),
    files: List[UploadFile] = File(...)
):
    if rack_name not in RACK_MAP:
        raise HTTPException(status_code=400, detail=f"알 수 없는 랙: {rack_name}")

    images = await read_images(files)
    rack_number = RACK_MAP[rack_name]

    racks = await analyze_images_batch(images, start_rack_num=rack_number, single_rack=True)
    products = racks[0]["products"] if racks else []

    result = save_rack_scan(store, rack_name, products)
    return JSONResponse(result)


# ── 한번에 스캔 (여러 랙 묶음) ──
@app.post("/api/scan/bulk")
async def scan_bulk(
    store: str = Form(...),
    files: List[UploadFile] = File(...),
    rack_names: List[str] = Form(...)  # 파일 순서와 동일
):
    images = await read_images(files)

    # 파일을 rack_name 순서대로 묶기
    if len(rack_names) != len(images):
        raise HTTPException(status_code=400, detail="파일 수와 랙 이름 수가 다릅니다")

    # rack_name별로 그룹핑
    rack_image_map: dict = {}
    for img, rname in zip(images, rack_names):
        if rname not in rack_image_map:
            rack_image_map[rname] = []
        rack_image_map[rname].append(img)

    # 병렬 분석
    async def analyze_one(rname, imgs):
        rnum = RACK_MAP.get(rname, 99)
        racks = await analyze_images_batch(imgs, start_rack_num=rnum, single_rack=True)
        products = racks[0]["products"] if racks else []
        return save_rack_scan(store, rname, products)

    tasks = [analyze_one(rname, imgs) for rname, imgs in rack_image_map.items()]
    results = await asyncio.gather(*tasks)

    total_products = sum(r["products_count"] for r in results)
    total_changes = sum(1 for r in results if r["changes"]["has_changes"])

    return JSONResponse({
        "store": store,
        "rack_count": len(results),
        "total_products": total_products,
        "changed_racks": total_changes,
        "racks": results,
    })


# ── 이어서 스캔 (단일 랙 추가) ──
@app.post("/api/scan/append")
async def scan_append(
    store: str = Form(...),
    rack_name: str = Form(...),
    files: List[UploadFile] = File(...)
):
    return await scan_rack(store=store, rack_name=rack_name, files=files)


# ============================================================
# 조회 API
# ============================================================

# ── 매장 전체 현황 ──
@app.get("/api/overview/{store}")
async def overview(store: str):
    data = get_store_overview(store)
    return JSONResponse(data)

# ── 최근 변동 이력 ──
@app.get("/api/changes/{store}")
async def changes(store: str, limit: int = 50):
    data = get_recent_changes(store, limit)
    return JSONResponse(data)

# ── 특정 랙 이력 ──
@app.get("/api/rack/{store}/{rack_name}/history")
async def rack_history(store: str, rack_name: str):
    data = get_rack_history(store, rack_name)
    return JSONResponse(data)

# ── SKU 검색 ──
@app.get("/api/search/{store}")
async def search(store: str, sku: str):
    data = search_sku(store, sku)
    return JSONResponse(data)


# ============================================================
# 관리 API
# ============================================================

# ── 랙 삭제 ──
@app.delete("/api/rack/{store}/{rack_name}")
async def delete_rack_api(store: str, rack_name: str):
    delete_rack(store, rack_name)
    return JSONResponse({"success": True})


# ============================================================
# 엑셀 다운로드
# ============================================================
@app.get("/api/excel/{store}")
async def download_excel(store: str):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl 미설치")

    data = get_excel_data(store)
    overview = data["overview"]
    changes = data["changes"]

    wb = openpyxl.Workbook()

    def style_header(ws, headers, color):
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=color)
            cell.alignment = Alignment(horizontal="center")

    store_label = {"gimhae": "김해", "jeonggwan": "정관"}.get(store, store)

    # 시트1: 전체 현황
    ws1 = wb.active
    ws1.title = "전체현황"
    style_header(ws1, ["랙이름", "랙번호", "품번", "정가", "할인가", "할인율", "최근스캔"], "FF4D00")
    for rack in overview["racks"]:
        for p in rack["products"]:
            ws1.append([
                rack["rack_name"], rack["rack_number"],
                p.get("sku", ""), p.get("price", ""),
                p.get("sale_price", ""),
                f"{p['discount_rate']}%" if p.get("discount_rate") else "",
                rack["last_scanned_at"]
            ])

    # 시트2: 변동 이력
    ws2 = wb.create_sheet("변동이력")
    style_header(ws2, ["스캔일시", "랙이름", "신규", "삭제", "변동", "제품수"], "E3B341")
    for h in changes:
        ch = h.get("changes", {})
        s = ch.get("summary", {})
        ws2.append([
            h["scanned_at"], h["rack_name"],
            s.get("added", 0), s.get("removed", 0), s.get("changed", 0),
            h["product_count"]
        ])

    # 열 너비 자동
    for ws in [ws1, ws2]:
        for col in ws.columns:
            w = max((len(str(c.value or "")) for c in col), default=0)
            ws.column_dimensions[col[0].column_letter].width = max(12, w + 2)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    from urllib.parse import quote
    date_str = __import__('datetime').datetime.now().strftime("%Y%m%d")
    filename = f"rack_{store}_{date_str}.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
