import os
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
# 랙 맵 (매장별 분리)
# ============================================================

RACK_MAP_GIMHAE = {
    "왼_벽랙": 1,  "뒷_벽랙": 2,  "오른_벽랙": 3,
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

RACK_MAP_JEONGGWAN = {
    "왼_벽랙": 1,  "뒷_벽랙": 2,  "오른_벽랙": 3,
    "1_양면A": 4,  "1_양면B": 5,
    "2_양면A": 6,  "2_양면B": 7,
    "3_양면A": 8,  "3_양면B": 9,
    "4_양면A": 10, "4_양면B": 11,
    "중간A_랙": 12,
    "5_양면A": 13, "5_양면B": 14,
    "6_양면A": 15, "6_양면B": 16,
    "7_양면A": 17, "7_양면B": 18,
    "8_양면A": 19, "8_양면B": 20,
    "중간B_랙": 21,
    "9_양면A": 22, "9_양면B": 23,
    "10_양면A": 24,"10_양면B": 25,
    "11_양면A": 26,"11_양면B": 27,
    "12_양면A": 28,"12_양면B": 29,
    "13_양면A": 30,"13_양면B": 31,
    "14_양면A": 32,"14_양면B": 33,
}

def get_rack_number(store: str, rack_name: str) -> int:
    m = RACK_MAP_JEONGGWAN if store == "jeonggwan" else RACK_MAP_GIMHAE
    return m.get(rack_name, 99)


# ============================================================
# 변동 감지
# ============================================================

def detect_changes(old_products: list, new_products: list) -> dict:
    old_map = {p["sku"]: p for p in old_products if p.get("sku")}
    new_map = {p["sku"]: p for p in new_products if p.get("sku")}

    added, removed, changed = [], [], []

    for sku, p in new_map.items():
        if sku not in old_map:
            added.append(sku)
        else:
            diffs = [
                {"field": f, "old": old_map[sku].get(f), "new": p.get(f)}
                for f in ["price", "sale_price", "discount_rate"]
                if old_map[sku].get(f) != p.get(f)
            ]
            if diffs:
                changed.append({"sku": sku, "changes": diffs})

    removed = [sku for sku in old_map if sku not in new_map]

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
    rack_number = get_rack_number(store, rack_name)
    scanned_at = now()

    existing = db.table("rack_master")\
        .select("products")\
        .eq("store", store)\
        .eq("rack_name", rack_name)\
        .execute().data

    old_products = existing[0]["products"] if existing else []
    changes = detect_changes(old_products, products)

    db.table("rack_master").upsert({
        "store": store,
        "rack_name": rack_name,
        "rack_number": rack_number,
        "products": products,
        "product_count": len(products),
        "last_scanned_at": scanned_at,
    }, on_conflict="store,rack_name").execute()

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
# 조회 함수
# ============================================================

def get_store_overview(store: str) -> dict:
    db = get_client()
    racks = db.table("rack_master")\
        .select("rack_name,rack_number,products,product_count,last_scanned_at")\
        .eq("store", store)\
        .order("rack_number")\
        .execute().data

    return {
        "store": store,
        "racks": racks,
        "rack_count": len(racks),
        "total_products": sum(r["product_count"] for r in racks),
        "discounted_count": sum(
            1 for r in racks for p in r["products"]
            if p.get("sale_price") or p.get("discount_rate")
        ),
    }


def get_recent_changes(store: str, limit: int = 50) -> list:
    return db_query_changes(store, limit)

def db_query_changes(store: str, limit: int) -> list:
    db = get_client()
    return db.table("rack_history")\
        .select("rack_name,rack_number,changes,scanned_at,product_count")\
        .eq("store", store)\
        .order("scanned_at", desc=True)\
        .limit(limit)\
        .execute().data


def get_rack_history(store: str, rack_name: str, limit: int = 10) -> list:
    db = get_client()
    return db.table("rack_history")\
        .select("products,product_count,changes,scanned_at")\
        .eq("store", store)\
        .eq("rack_name", rack_name)\
        .order("scanned_at", desc=True)\
        .limit(limit)\
        .execute().data


def search_sku(store: str, sku: str) -> list:
    db = get_client()
    racks = db.table("rack_master")\
        .select("rack_name,rack_number,products")\
        .eq("store", store)\
        .execute().data

    sku_lower = sku.lower()
    return [
        {"rack_name": r["rack_name"], "rack_number": r["rack_number"], "product": p}
        for r in racks
        for p in r["products"]
        if sku_lower in (p.get("sku") or "").lower()
    ]


def delete_rack(store: str, rack_name: str):
    db = get_client()
    db.table("rack_master")\
        .delete()\
        .eq("store", store)\
        .eq("rack_name", rack_name)\
        .execute()


def get_excel_data(store: str) -> dict:
    return {
        "overview": get_store_overview(store),
        "changes": db_query_changes(store, limit=200),
    }
