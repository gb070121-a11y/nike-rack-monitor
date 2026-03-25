from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import base64
import io
import os
from typing import List
from database import (init_db, save_scan_session, get_sessions, get_session_detail,
                      compare_sessions, append_scan_to_session, replace_rack_in_session,
                      create_empty_session, finish_session, delete_session,
                      delete_rack_products, move_products_to_rack, delete_products)
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
    tasks = {rack_num: analyze_images_batch(imgs, start_rack_num=rack_num, single_rack=True)
             for rack_num, imgs in rack_dict.items()}
    results = await asyncio.gather(*tasks.values())
    for rack_num, racks in zip(tasks.keys(), results):
        products = [p for r in racks for p in r["products"]]
        all_racks.append({"rack_number": rack_num, "products": products, "photo_count": len(rack_dict[rack_num])})
    return sorted(all_racks, key=lambda x: x["rack_number"])


# ── 스캔 API ──
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
                         "product_count": sum(len(r["products"]) for r in all_racks),
                         "diff": diff})

@app.post("/api/scan/start")
async def start_session(store: str = Form(...)):
    session_id = create_empty_session(store)
    return JSONResponse({"session_id": session_id, "store": store})

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

@app.post("/api/scan/finish/{session_id}")
async def finish_session_api(session_id: int):
    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="세션 없음")
    finish_session(session_id)
    updated = get_session_detail(session_id)
    diff = compare_sessions(detail["store"], session_id)
    return JSONResponse({"session_id": session_id, "store": detail["store"],
                         "total_racks": len(updated["racks"]),
                         "total_products": sum(len(r["products"]) for r in updated["racks"]),
                         "diff": diff})

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

@app.post("/api/scan")
async def upload_scan(store: str = Form(...), files: List[UploadFile] = File(...)):
    images = await read_images(files)
    racks = await analyze_images_batch(images)
    session_id = save_scan_session(store, racks)
    diff = compare_sessions(store, session_id)
    return JSONResponse({"session_id": session_id, "store": store, "racks": racks, "diff": diff})


# ── 조회 ──
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


# ── 데이터 관리 ──
@app.delete("/api/sessions/{session_id}")
async def delete_session_api(session_id: int):
    delete_session(session_id)
    return JSONResponse({"success": True})

@app.delete("/api/sessions/{session_id}/racks/{rack_number}/products")
async def delete_rack_products_api(session_id: int, rack_number: int):
    """랙 번호는 유지, 안의 제품만 삭제"""
    delete_rack_products(session_id, rack_number)
    return JSONResponse({"success": True})

@app.delete("/api/products/{product_id}")
async def delete_product_api(product_id: int):
    delete_products([product_id])
    return JSONResponse({"success": True})

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
async def download_excel(session_id: int):
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

    def style_header(ws, headers, color):
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=color)
            cell.alignment = Alignment(horizontal="center")

    # 시트1: 전체현황
    ws1 = wb.active
    ws1.title = "All"
    style_header(ws1, ["Rack","SKU","Name","Price","Sale","Discount"], "FF4D00")
    for rack in detail["racks"]:
        for p in rack["products"]:
            ws1.append([rack["rack_number"], p.get("sku",""), p.get("name",""),
                        p.get("price",""), p.get("sale_price",""),
                        f"{p['discount_rate']}%" if p.get("discount_rate") else ""])

    # 시트2: 신규
    ws2 = wb.create_sheet("Added")
    style_header(ws2, ["Rack","SKU","Name","Price","Sale","Discount"], "39D353")
    if diff.get("has_previous"):
        for c in diff["changes"]:
            if c["type"] == "added":
                ws2.append([c["rack"], c["sku"], c.get("name",""),
                            c.get("new_price",""), c.get("new_sale_price",""),
                            f"{c['new_discount']}%" if c.get("new_discount") else ""])

    # 시트3: 사라짐
    ws3 = wb.create_sheet("Removed")
    style_header(ws3, ["Rack","SKU","Name","OldPrice","OldSale","OldDiscount"], "F85149")
    if diff.get("has_previous"):
        for c in diff["changes"]:
            if c["type"] == "removed":
                ws3.append([c["rack"], c["sku"], c.get("name",""),
                            c.get("old_price",""), c.get("old_sale_price",""),
                            f"{c['old_discount']}%" if c.get("old_discount") else ""])

    # 시트4: 가격변동
    ws4 = wb.create_sheet("Changed")
    style_header(ws4, ["Rack","SKU","Name","Field","Old","New"], "E3B341")
    if diff.get("has_previous"):
        fl = {"price":"Price","sale_price":"Sale","discount_rate":"Discount","rack":"Rack"}
        for c in diff["changes"]:
            if c["type"] == "changed":
                for ch in c["changes"]:
                    ws4.append([c["rack"], c["sku"], c.get("name",""),
                                fl.get(ch["field"],ch["field"]), ch["old"], ch["new"]])

    for ws in [ws1, ws2, ws3, ws4]:
        for col in ws.columns:
            w = max((len(str(cell.value or "")) for cell in col), default=0)
            ws.column_dimensions[col[0].column_letter].width = max(12, w + 2)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    store = detail["store"]
    date = detail["scanned_at"][:10]
    filename = f"rack_{store}_{date}.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
