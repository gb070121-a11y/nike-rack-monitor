import sqlite3
import json
from datetime import datetime

DB_PATH = "nike_monitor.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store TEXT NOT NULL,
            scanned_at TEXT NOT NULL,
            rack_count INTEGER DEFAULT 0,
            product_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'complete'
        );
        CREATE TABLE IF NOT EXISTS racks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            rack_number INTEGER NOT NULL,
            photo_count INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rack_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            store TEXT NOT NULL,
            rack_number INTEGER NOT NULL,
            sku TEXT NOT NULL,
            name TEXT,
            price INTEGER,
            sale_price INTEGER,
            discount_rate INTEGER,
            position INTEGER,
            FOREIGN KEY (rack_id) REFERENCES racks(id)
        );
        CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
        CREATE INDEX IF NOT EXISTS idx_products_session ON products(session_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_store ON sessions(store);
    """)
    conn.commit()
    conn.close()


def create_empty_session(store: str) -> int:
    """이어서 업로드용 빈 세션 생성"""
    conn = get_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        "INSERT INTO sessions (store, scanned_at, rack_count, product_count, status) VALUES (?, ?, 0, 0, 'in_progress')",
        (store, now)
    )
    session_id = cur.lastrowid
    conn.commit()
    conn.close()
    return session_id


def save_scan_session(store: str, racks: list) -> int:
    conn = get_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_products = sum(len(r["products"]) for r in racks)
    cur = conn.execute(
        "INSERT INTO sessions (store, scanned_at, rack_count, product_count, status) VALUES (?, ?, ?, ?, 'complete')",
        (store, now, len(racks), total_products)
    )
    session_id = cur.lastrowid
    _insert_racks(conn, session_id, store, racks)
    conn.commit()
    conn.close()
    return session_id


def append_scan_to_session(session_id: int, racks: list):
    """이어서 업로드 — 기존 세션에 랙 추가"""
    conn = get_conn()
    store = conn.execute("SELECT store FROM sessions WHERE id=?", (session_id,)).fetchone()["store"]
    _insert_racks(conn, session_id, store, racks)

    # 세션 통계 업데이트
    total_racks = conn.execute("SELECT COUNT(*) FROM racks WHERE session_id=?", (session_id,)).fetchone()[0]
    total_products = conn.execute("SELECT COUNT(*) FROM products WHERE session_id=?", (session_id,)).fetchone()[0]
    conn.execute(
        "UPDATE sessions SET rack_count=?, product_count=? WHERE id=?",
        (total_racks, total_products, session_id)
    )
    conn.commit()
    conn.close()


def replace_rack_in_session(session_id: int, rack_number: int, products: list):
    """랙별 업로드 — 특정 랙 번호의 데이터만 교체"""
    conn = get_conn()
    store = conn.execute("SELECT store FROM sessions WHERE id=?", (session_id,)).fetchone()["store"]

    # 기존 랙 삭제
    old_rack = conn.execute(
        "SELECT id FROM racks WHERE session_id=? AND rack_number=?", (session_id, rack_number)
    ).fetchone()
    if old_rack:
        conn.execute("DELETE FROM products WHERE rack_id=?", (old_rack["id"],))
        conn.execute("DELETE FROM racks WHERE id=?", (old_rack["id"],))

    # 새 랙 삽입
    rack_cur = conn.execute(
        "INSERT INTO racks (session_id, rack_number, photo_count) VALUES (?, ?, ?)",
        (session_id, rack_number, len(products))
    )
    rack_id = rack_cur.lastrowid
    for p in products:
        conn.execute(
            """INSERT INTO products (rack_id, session_id, store, rack_number, sku, name, price, sale_price, discount_rate, position)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rack_id, session_id, store, rack_number,
             p.get("sku", "UNKNOWN"), p.get("name"), p.get("price"),
             p.get("sale_price"), p.get("discount_rate"), p.get("position", 0))
        )

    # 세션 통계 업데이트
    total_racks = conn.execute("SELECT COUNT(*) FROM racks WHERE session_id=?", (session_id,)).fetchone()[0]
    total_products = conn.execute("SELECT COUNT(*) FROM products WHERE session_id=?", (session_id,)).fetchone()[0]
    conn.execute(
        "UPDATE sessions SET rack_count=?, product_count=? WHERE id=?",
        (total_racks, total_products, session_id)
    )
    conn.commit()
    conn.close()


def _insert_racks(conn, session_id: int, store: str, racks: list):
    for rack in racks:
        rack_cur = conn.execute(
            "INSERT INTO racks (session_id, rack_number, photo_count) VALUES (?, ?, ?)",
            (session_id, rack["rack_number"], rack.get("photo_count", 0))
        )
        rack_id = rack_cur.lastrowid
        for p in rack["products"]:
            conn.execute(
                """INSERT INTO products (rack_id, session_id, store, rack_number, sku, name, price, sale_price, discount_rate, position)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rack_id, session_id, store, rack["rack_number"],
                 p.get("sku", "UNKNOWN"), p.get("name"), p.get("price"),
                 p.get("sale_price"), p.get("discount_rate"), p.get("position", 0))
            )


def get_sessions(store: str = None) -> list:
    conn = get_conn()
    if store:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE store=? ORDER BY scanned_at DESC LIMIT 50", (store,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY scanned_at DESC LIMIT 50"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_detail(session_id: int) -> dict:
    conn = get_conn()
    session = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        conn.close()
        return None
    racks_raw = conn.execute(
        "SELECT * FROM racks WHERE session_id=? ORDER BY rack_number", (session_id,)
    ).fetchall()
    racks = []
    for rack in racks_raw:
        products = conn.execute(
            "SELECT * FROM products WHERE rack_id=? ORDER BY position", (rack["id"],)
        ).fetchall()
        racks.append({**dict(rack), "products": [dict(p) for p in products]})
    conn.close()
    return {**dict(session), "racks": racks}


def compare_sessions(store: str, new_session_id: int, old_session_id: int = None) -> dict:
    conn = get_conn()
    if old_session_id is None:
        prev = conn.execute(
            "SELECT id FROM sessions WHERE store=? AND id < ? AND status='complete' ORDER BY id DESC LIMIT 1",
            (store, new_session_id)
        ).fetchone()
        if not prev:
            conn.close()
            return {"has_previous": False, "changes": []}
        old_session_id = prev["id"]

    def get_products_dict(sid):
        rows = conn.execute("SELECT * FROM products WHERE session_id=?", (sid,)).fetchall()
        d = {}
        for r in rows:
            key = f"{r['rack_number']}:{r['sku']}"
            d[key] = dict(r)
        return d

    old_products = get_products_dict(old_session_id)
    new_products = get_products_dict(new_session_id)
    old_session = conn.execute("SELECT * FROM sessions WHERE id=?", (old_session_id,)).fetchone()
    conn.close()

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
        "compared_with_date": dict(old_session)["scanned_at"] if old_session else None,
        "summary": {
            "added": len([c for c in changes if c["type"] == "added"]),
            "removed": len([c for c in changes if c["type"] == "removed"]),
            "changed": len([c for c in changes if c["type"] == "changed"]),
        },
        "changes": changes
    }
