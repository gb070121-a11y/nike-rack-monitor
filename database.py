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


def init_db():
    """Supabase 테이블 생성 확인 — 테이블은 Supabase 대시보드에서 생성"""
    pass


def create_empty_session(store: str) -> int:
    db = get_client()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    res = db.table("sessions").insert({
        "store": store,
        "scanned_at": now,
        "rack_count": 0,
        "product_count": 0,
        "status": "in_progress"
    }).execute()
    return res.data[0]["id"]


def save_scan_session(store: str, racks: list) -> int:
    db = get_client()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_products = sum(len(r["products"]) for r in racks)

    res = db.table("sessions").insert({
        "store": store,
        "scanned_at": now,
        "rack_count": len(racks),
        "product_count": total_products,
        "status": "complete"
    }).execute()
    session_id = res.data[0]["id"]
    _insert_racks(db, session_id, store, racks)
    return session_id


def append_scan_to_session(session_id: int, racks: list):
    db = get_client()
    store = db.table("sessions").select("store").eq("id", session_id).execute().data[0]["store"]
    _insert_racks(db, session_id, store, racks)
    _update_session_stats(db, session_id)


def replace_rack_in_session(session_id: int, rack_number: int, products: list):
    db = get_client()
    store = db.table("sessions").select("store").eq("id", session_id).execute().data[0]["store"]

    # 기존 랙 찾기
    old_racks = db.table("racks").select("id").eq("session_id", session_id).eq("rack_number", rack_number).execute().data
    if old_racks:
        old_rack_id = old_racks[0]["id"]
        db.table("products").delete().eq("rack_id", old_rack_id).execute()
        db.table("racks").delete().eq("id", old_rack_id).execute()

    # 새 랙 삽입
    rack_res = db.table("racks").insert({
        "session_id": session_id,
        "rack_number": rack_number,
        "photo_count": len(products)
    }).execute()
    rack_id = rack_res.data[0]["id"]

    if products:
        db.table("products").insert([{
            "rack_id": rack_id,
            "session_id": session_id,
            "store": store,
            "rack_number": rack_number,
            "sku": p.get("sku", "UNKNOWN"),
            "name": p.get("name"),
            "price": p.get("price"),
            "sale_price": p.get("sale_price"),
            "discount_rate": p.get("discount_rate"),
            "position": p.get("position", 0)
        } for p in products]).execute()

    _update_session_stats(db, session_id)


def _insert_racks(db, session_id: int, store: str, racks: list):
    for rack in racks:
        rack_res = db.table("racks").insert({
            "session_id": session_id,
            "rack_number": rack["rack_number"],
            "photo_count": rack.get("photo_count", 0)
        }).execute()
        rack_id = rack_res.data[0]["id"]

        if rack["products"]:
            db.table("products").insert([{
                "rack_id": rack_id,
                "session_id": session_id,
                "store": store,
                "rack_number": rack["rack_number"],
                "sku": p.get("sku", "UNKNOWN"),
                "name": p.get("name"),
                "price": p.get("price"),
                "sale_price": p.get("sale_price"),
                "discount_rate": p.get("discount_rate"),
                "position": p.get("position", 0)
            } for p in rack["products"]]).execute()


def _update_session_stats(db, session_id: int):
    racks = db.table("racks").select("id").eq("session_id", session_id).execute().data
    products = db.table("products").select("id").eq("session_id", session_id).execute().data
    db.table("sessions").update({
        "rack_count": len(racks),
        "product_count": len(products)
    }).eq("id", session_id).execute()


def get_sessions(store: str = None) -> list:
    db = get_client()
    query = db.table("sessions").select("*").order("scanned_at", desc=True).limit(50)
    if store:
        query = query.eq("store", store)
    return query.execute().data


def get_session_detail(session_id: int) -> dict:
    db = get_client()
    session = db.table("sessions").select("*").eq("id", session_id).execute().data
    if not session:
        return None
    session = session[0]

    racks_raw = db.table("racks").select("*").eq("session_id", session_id).order("rack_number").execute().data
    racks = []
    for rack in racks_raw:
        products = db.table("products").select("*").eq("rack_id", rack["id"]).order("position").execute().data
        racks.append({**rack, "products": products})

    return {**session, "racks": racks}


def finish_session(session_id: int):
    db = get_client()
    db.table("sessions").update({"status": "complete"}).eq("id", session_id).execute()
    _update_session_stats(db, session_id)


def compare_sessions(store: str, new_session_id: int, old_session_id: int = None) -> dict:
    db = get_client()

    if old_session_id is None:
        prev = db.table("sessions").select("id").eq("store", store).eq("status", "complete").lt("id", new_session_id).order("id", desc=True).limit(1).execute().data
        if not prev:
            return {"has_previous": False, "changes": []}
        old_session_id = prev[0]["id"]

    def get_products_dict(sid):
        rows = db.table("products").select("*").eq("session_id", sid).execute().data
        d = {}
        for r in rows:
            key = f"{r['rack_number']}:{r['sku']}"
            d[key] = r
        return d

    old_products = get_products_dict(old_session_id)
    new_products = get_products_dict(new_session_id)
    old_session = db.table("sessions").select("*").eq("id", old_session_id).execute().data
    old_session = old_session[0] if old_session else None

    changes = []
    all_keys = set(old_products.keys()) | set(new_products.keys())

    for key in all_keys:
        old = old_products.get(key)
        new = new_products.get(key)

        if old and not new:
            changes.append({
                "type": "removed", "rack": old["rack_number"], "sku": old["sku"],
                "name": old.get("name"), "old_price": old.get("price"),
                "old_sale_price": old.get("sale_price"), "old_discount": old.get("discount_rate"),
            })
        elif new and not old:
            changes.append({
                "type": "added", "rack": new["rack_number"], "sku": new["sku"],
                "name": new.get("name"), "new_price": new.get("price"),
                "new_sale_price": new.get("sale_price"), "new_discount": new.get("discount_rate"),
            })
        else:
            price_changed = old.get("price") != new.get("price")
            sale_changed = old.get("sale_price") != new.get("sale_price")
            discount_changed = old.get("discount_rate") != new.get("discount_rate")
            rack_changed = old.get("rack_number") != new.get("rack_number")
            if price_changed or sale_changed or discount_changed or rack_changed:
                change = {"type": "changed", "rack": new["rack_number"], "sku": new["sku"],
                          "name": new.get("name"), "changes": []}
                if price_changed:
                    change["changes"].append({"field": "price", "old": old.get("price"), "new": new.get("price")})
                if sale_changed:
                    change["changes"].append({"field": "sale_price", "old": old.get("sale_price"), "new": new.get("sale_price")})
                if discount_changed:
                    change["changes"].append({"field": "discount_rate", "old": old.get("discount_rate"), "new": new.get("discount_rate")})
                if rack_changed:
                    change["changes"].append({"field": "rack", "old": old.get("rack_number"), "new": new.get("rack_number")})
                changes.append(change)

    return {
        "has_previous": True,
        "compared_with_session": old_session_id,
        "compared_with_date": old_session["scanned_at"] if old_session else None,
        "summary": {
            "added": len([c for c in changes if c["type"] == "added"]),
            "removed": len([c for c in changes if c["type"] == "removed"]),
            "changed": len([c for c in changes if c["type"] == "changed"]),
        },
        "changes": changes
    }
