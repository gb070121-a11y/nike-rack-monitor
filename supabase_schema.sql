-- Nike Rack Monitor 테이블 생성

CREATE TABLE IF NOT EXISTS sessions (
    id BIGSERIAL PRIMARY KEY,
    store TEXT NOT NULL,
    scanned_at TEXT NOT NULL,
    rack_count INTEGER DEFAULT 0,
    product_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'complete'
);

CREATE TABLE IF NOT EXISTS racks (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    rack_number INTEGER NOT NULL,
    photo_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    rack_id BIGINT NOT NULL REFERENCES racks(id) ON DELETE CASCADE,
    session_id BIGINT NOT NULL,
    store TEXT NOT NULL,
    rack_number INTEGER NOT NULL,
    sku TEXT NOT NULL,
    name TEXT,
    price INTEGER,
    sale_price INTEGER,
    discount_rate INTEGER,
    position INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
CREATE INDEX IF NOT EXISTS idx_products_session ON products(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_store ON sessions(store);

-- RLS 비활성화 (내부 서비스용)
ALTER TABLE sessions DISABLE ROW LEVEL SECURITY;
ALTER TABLE racks DISABLE ROW LEVEL SECURITY;
ALTER TABLE products DISABLE ROW LEVEL SECURITY;

-- 랙 구간 스캔 세션 테이블 (구간별 스캔 관리)
CREATE TABLE IF NOT EXISTS rack_range_sessions (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    rack_from INTEGER NOT NULL,
    rack_to INTEGER NOT NULL,
    scanned_at TEXT NOT NULL
);
