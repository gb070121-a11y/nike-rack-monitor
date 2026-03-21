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
            product_count INTEGER DEFAULT 0
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


def save_scan_session(store: str, racks: list) -> int:
    conn = get_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total_products = sum(len(r["products"]) for r in racks)

    cur = conn.execute(
        "INSERT INTO sessions (store, scanned_at, rack_count, product_count) VALUES (?, ?, ?, ?)",
        (store, now, len(racks), total_products)
    )
    session_id = cur.lastrowid

    for rack in racks:
        rack_cur = conn.execute(
            "INSERT INTO racks (session_id, rack_number, photo_count) VALUES (?, ?, ?)",
            (session_id, rack["rack_number"], rack.get("photo_count", 0))
        )
        rack_id = rack_cur.lastrowid

        for p in rack["products"]:
            conn.execute(
                """INSERT INTO products
                   (rack_id, session_id, store, rack_number, sku, name, price, sale_price, discount_rate, position)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rack_id, session_id, store,
                    rack["rack_number"],
                    p.get("sku", "UNKNOWN"),
                    p.get("name"),
                    p.get("price"),
                    p.get("sale_price"),
                    p.get("discount_rate"),
                    p.get("position", 0)
                )
            )

    conn.commit()
    conn.close()
    return session_id


def get_sessions(store: str = None) -> list:
    conn = get_conn()
    if store:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE store=? ORDER BY scanned_at DESC LIMIT 50",
            (store,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY scanned_at DESC LIMIT 50"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_detail(session_id: int) -> dict:
    conn = get_conn()
    session = conn.execute(
        "SELECT * FROM sessions WHERE id=?", (session_id,)
    ).fetchone()
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
        racks.append({
            **dict(rack),
            "products": [dict(p) for p in products]
        })

    conn.close()
    return {**dict(session), "racks": racks}


def compare_sessions(store: str, new_session_id: int, old_session_id: int = None) -> dict:
    """
    새 세션과 이전 세션 비교.
    old_session_id가 없으면 같은 매장의 직전 세션과 비교.
    """
    conn = get_conn()

    if old_session_id is None:
        prev = conn.execute(
            """SELECT id FROM sessions
               WHERE store=? AND id < ?
               ORDER BY id DESC LIMIT 1""",
            (store, new_session_id)
        ).fetchone()
        if not prev:
            conn.close()
            return {"has_previous": False, "changes": []}
        old_session_id = prev["id"]

    # 이전/새 제품 딕셔너리 (sku → 제품정보)
    def get_products_dict(sid):
        rows = conn.execute(
            "SELECT * FROM products WHERE session_id=?", (sid,)
        ).fetchall()
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
                "type": "removed",
                "rack": old["rack_number"],
                "sku": old["sku"],
                "name": old.get("name"),
                "old_price": old.get("price"),
                "old_sale_price": old.get("sale_price"),
                "old_discount": old.get("discount_rate"),
            })
        elif new and not old:
            changes.append({
                "type": "added",
                "rack": new["rack_number"],
                "sku": new["sku"],
                "name": new.get("name"),
                "new_price": new.get("price"),
                "new_sale_price": new.get("sale_price"),
                "new_discount": new.get("discount_rate"),
            })
        else:
            # 가격/할인 변동 체크
            price_changed = old.get("price") != new.get("price")
            sale_changed = old.get("sale_price") != new.get("sale_price")
            discount_changed = old.get("discount_rate") != new.get("discount_rate")
            rack_changed = old.get("rack_number") != new.get("rack_number")

            if price_changed or sale_changed or discount_changed or rack_changed:
                change = {
                    "type": "changed",
                    "rack": new["rack_number"],
                    "sku": new["sku"],
                    "name": new.get("name"),
                    "changes": []
                }
                if price_changed:
                    change["changes"].append({
                        "field": "price",
                        "old": old.get("price"),
                        "new": new.get("price")
                    })
                if sale_changed:
                    change["changes"].append({
                        "field": "sale_price",
                        "old": old.get("sale_price"),
                        "new": new.get("sale_price")
                    })
                if discount_changed:
                    change["changes"].append({
                        "field": "discount_rate",
                        "old": old.get("discount_rate"),
                        "new": new.get("discount_rate")
                    })
                if rack_changed:
                    change["changes"].append({
                        "field": "rack",
                        "old": old.get("rack_number"),
                        "new": new.get("rack_number")
                    })
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
