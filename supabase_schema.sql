-- =============================================
-- Nike Rack Monitor v2 - 완전 재설계
-- Supabase SQL Editor에서 실행하세요
-- =============================================

-- 기존 테이블 삭제 (순서 중요)
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS racks CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS rack_products CASCADE;
DROP TABLE IF EXISTS rack_master CASCADE;
DROP TABLE IF EXISTS rack_history CASCADE;

-- =============================================
-- 1. rack_master: 랙별 현재 최신 상태
-- =============================================
CREATE TABLE rack_master (
    id BIGSERIAL PRIMARY KEY,
    store TEXT NOT NULL,           -- 'gimhae' | 'jeonggwan'
    rack_name TEXT NOT NULL,       -- '1_양면A', '왼_벽랙' 등
    rack_number INTEGER NOT NULL,  -- 정렬/비교용 숫자
    last_scanned_at TIMESTAMPTZ,
    product_count INTEGER DEFAULT 0,
    UNIQUE(store, rack_name)
);

-- =============================================
-- 2. rack_products: 현재 제품 목록 (항상 최신)
-- =============================================
CREATE TABLE rack_products (
    id BIGSERIAL PRIMARY KEY,
    store TEXT NOT NULL,
    rack_name TEXT NOT NULL,
    rack_number INTEGER NOT NULL,
    sku TEXT NOT NULL,
    name TEXT,
    price INTEGER,
    sale_price INTEGER,
    discount_rate INTEGER,
    position INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- 3. rack_history: 스캔 이력 (변경사항 기록)
-- =============================================
CREATE TABLE rack_history (
    id BIGSERIAL PRIMARY KEY,
    store TEXT NOT NULL,
    rack_name TEXT NOT NULL,
    scanned_at TIMESTAMPTZ DEFAULT NOW(),
    product_count INTEGER DEFAULT 0,
    changes JSONB DEFAULT '[]',    -- [{type, sku, name, ...}]
    products_snapshot JSONB DEFAULT '[]'  -- 스캔 당시 전체 제품
);

-- =============================================
-- 인덱스 (성능 최적화)
-- =============================================
CREATE INDEX idx_rack_products_store_rack ON rack_products(store, rack_name);
CREATE INDEX idx_rack_products_sku ON rack_products(sku);
CREATE INDEX idx_rack_products_store ON rack_products(store);
CREATE INDEX idx_rack_master_store ON rack_master(store);
CREATE INDEX idx_rack_master_store_rack ON rack_master(store, rack_name);
CREATE INDEX idx_rack_history_store_rack ON rack_history(store, rack_name);
CREATE INDEX idx_rack_history_scanned ON rack_history(store, scanned_at DESC);

-- =============================================
-- RLS 비활성화 (내부 서비스용)
-- =============================================
ALTER TABLE rack_master DISABLE ROW LEVEL SECURITY;
ALTER TABLE rack_products DISABLE ROW LEVEL SECURITY;
ALTER TABLE rack_history DISABLE ROW LEVEL SECURITY;

-- =============================================
-- 김해 매장 기본 랙 데이터 삽입
-- =============================================
INSERT INTO rack_master (store, rack_name, rack_number) VALUES
('gimhae', '왼_벽랙', 1),
('gimhae', '뒷_벽랙', 2),
('gimhae', '오른_벽랙', 3),
('gimhae', '1_양면A', 4), ('gimhae', '1_양면B', 5),
('gimhae', '2_양면A', 6), ('gimhae', '2_양면B', 7),
('gimhae', '3_양면A', 8), ('gimhae', '3_양면B', 9),
('gimhae', '4_양면A', 10), ('gimhae', '4_양면B', 11),
('gimhae', '5_양면A', 12), ('gimhae', '5_양면B', 13),
('gimhae', '중간A_랙', 14),
('gimhae', '6_양면A', 15), ('gimhae', '6_양면B', 16),
('gimhae', '7_양면A', 17), ('gimhae', '7_양면B', 18),
('gimhae', '8_양면A', 19), ('gimhae', '8_양면B', 20),
('gimhae', '9_양면A', 21), ('gimhae', '9_양면B', 22),
('gimhae', '10_양면A', 23), ('gimhae', '10_양면B', 24),
('gimhae', '중간B_랙', 25),
('gimhae', '11_양면A', 26), ('gimhae', '11_양면B', 27),
('gimhae', '12_양면A', 28), ('gimhae', '12_양면B', 29),
('gimhae', '13_양면A', 30), ('gimhae', '13_양면B', 31),
('gimhae', '14_양면A', 32), ('gimhae', '14_양면B', 33),
('gimhae', '15_양면A', 34), ('gimhae', '15_양면B', 35);

INSERT INTO rack_master (store, rack_name, rack_number) VALUES
('jeonggwan', '왼_벽랙', 1),
('jeonggwan', '뒷_벽랙', 2),
('jeonggwan', '오른_벽랙', 3);
