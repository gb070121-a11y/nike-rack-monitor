import os
import json
from datetime import datetime
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://sdchxrvmzekoymmwihim.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

_client = None

def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def init_db():
    pass


# ============================================================
# RACK_MAP: 랙 이름 → 번호 매핑
# ============================================================
RACK_MAP = {
    "왼_벽랙": 1, "뒷_벽랙": 2, "오른_벽랙": 3,
    "1_양면A": 4,  "1_양면B": 5,
    "2_양면A": 6,  "2_양면B": 7,
    "3_양면A": 8,  "3_양면B": 9,
    "4_양면A": 10, "4_양면B": 11,
    "5_양면A": 12, "5_양면B": 13,
    "중간A_랙": 14,
    "6_양면A": 15, "6_양면B": 16,
    "7_양면A": 17, "7_양면B": 18,
    "8_양면A": 19, "8_양면B": 20,
    "9_양면A": 21, "9_양면B": 22,
    "10_양면A": 23,"10_양면B": 24,
    "중간B_랙": 25,
    "11_양면A": 26,"11_양면B": 27,
    "12_양면A": 28,"12_양면B": 29,
    "13_양면A": 30,"13_양면B": 31,
    "14_양면A": 32,"14_양면B": 33,
    "15_양면A": 34,"15_양면B": 35,
}


# ============================================================
# 변동 감지: 이전 제품 vs 신규 제품 비교
# ============================================================
def detect_changes(old_products: list, new_products: list) -> dict:
    old_map = {p["sku"]: p for p in old_products if p.get("sku")}
    new_map = {p["sku"]: p for p in new_products if p.get("sku")}

    added, removed, changed = [], [], []

    for sku, p in new_map.items():
        if sku not in old_map:
            added.append(sku)
        else:
            diffs = []
            for field in ["price", "sale_price", "discount_rate"]:
                ov, nv = old_map[sku].get(field), p.get(field)
                if ov != nv:
                    diffs.append({"field": field, "old": ov, "new": nv})
            if diffs:
                changed.append({"sku": sku, "changes": diffs})

    for sku in old_map:
        if sku not in new_map:
            removed.append(sku)

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
        "has_changes": bool(added or removed or changed)
    }


# ============================================================
# 랙 스캔 저장 (upsert)
# ============================================================
def save_rack_scan(store: str, rack_name: str, products: list) -> dict:
    db = get_client()
    rack_number = RACK_MAP.get(rack_name, 99)
    scanned_at = now()

    # 기존 데이터 조회
    existing = db.table("rack_master")\
        .select("id,products")\
        .eq("store", store)\
        .eq("rack_name", rack_name)\
        .execute().data

    old_products = existing[0]["products"] if existing else []

    # 변동 감지
    changes = detect_changes(old_products, products)

    # rack_master upsert
    db.table("rack_master").upsert({
        "store": store,
        "rack_name": rack_name,
        "rack_number": rack_number,
        "products": products,
        "product_count": len(products),
        "last_scanned_at": scanned_at,
    }, on_conflict="store,rack_name").execute()

    # 이력 저장 (변동 있을 때만)
    if changes["has_changes"] or not existing:
        db.table("rack_history").insert({
            "store": store,
            "rack_name": rack_name,
            "rack_number": rack_number,
            "products": products,
            "product_count": len(products),
            "changes": changes,
            "scanned_at": scanned_at,
        }).execute()

    return {
        "rack_name": rack_name,
        "rack_number": rack_number,
        "products_count": len(products),
        "changes": changes,
        "scanned_at": scanned_at,
    }


# ============================================================
# 매장 전체 현황 조회 (캐시 최적화: 한 번에 가져오기)
# ============================================================
def get_store_overview(store: str) -> dict:
    db = get_client()

    racks = db.table("rack_master")\
        .select("rack_name,rack_number,products,product_count,last_scanned_at")\
        .eq("store", store)\
        .order("rack_number")\
        .execute().data

    total_products = sum(r["product_count"] for r in racks)
    discounted = sum(
        1 for r in racks for p in r["products"]
        if p.get("sale_price") or p.get("discount_rate")
    )

    return {
        "store": store,
        "racks": racks,
        "rack_count": len(racks),
        "total_products": total_products,
        "discounted_count": discounted,
    }


# ============================================================
# 최근 변동 이력 조회
# ============================================================
def get_recent_changes(store: str, limit: int = 50) -> list:
    db = get_client()
    rows = db.table("rack_history")\
        .select("rack_name,rack_number,changes,scanned_at,product_count")\
        .eq("store", store)\
        .order("scanned_at", desc=True)\
        .limit(limit)\
        .execute().data
    return rows


# ============================================================
# 특정 랙 이력 조회
# ============================================================
def get_rack_history(store: str, rack_name: str, limit: int = 10) -> list:
    db = get_client()
    rows = db.table("rack_history")\
        .select("products,product_count,changes,scanned_at")\
        .eq("store", store)\
        .eq("rack_name", rack_name)\
        .order("scanned_at", desc=True)\
        .limit(limit)\
        .execute().data
    return rows


# ============================================================
# SKU 검색
# ============================================================
def search_sku(store: str, sku: str) -> list:
    db = get_client()
    racks = db.table("rack_master")\
        .select("rack_name,rack_number,products")\
        .eq("store", store)\
        .execute().data

    results = []
    sku_lower = sku.lower()
    for rack in racks:
        for p in rack["products"]:
            if sku_lower in (p.get("sku") or "").lower():
                results.append({
                    "rack_name": rack["rack_name"],
                    "rack_number": rack["rack_number"],
                    "product": p
                })
    return results


# ============================================================
# 랙 제품 삭제 (랙 자체 삭제)
# ============================================================
def delete_rack(store: str, rack_name: str):
    db = get_client()
    db.table("rack_master")\
        .delete()\
        .eq("store", store)\
        .eq("rack_name", rack_name)\
        .execute()


# ============================================================
# 엑셀용 전체 데이터
# ============================================================
def get_excel_data(store: str) -> dict:
    overview = get_store_overview(store)
    changes = get_recent_changes(store, limit=200)
    return {"overview": overview, "changes": changes}
