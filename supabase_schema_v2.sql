-- ============================================
-- Nike Rack Monitor V2 Schema
-- rack_master 기반 설계
-- ============================================

-- 기존 테이블 삭제
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS racks CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;

-- ============================================
-- 1. rack_master: 각 랙의 현재 최신 상태
-- ============================================
CREATE TABLE IF NOT EXISTS rack_master (
    id BIGSERIAL PRIMARY KEY,
    store TEXT NOT NULL,
    rack_name TEXT NOT NULL,
    rack_number INTEGER NOT NULL,
    products JSONB NOT NULL DEFAULT '[]',
    product_count INTEGER NOT NULL DEFAULT 0,
    last_scanned_at TEXT NOT NULL,
    UNIQUE(store, rack_name)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_rack_master_store ON rack_master(store);
CREATE INDEX IF NOT EXISTS idx_rack_master_store_name ON rack_master(store, rack_name);
CREATE INDEX IF NOT EXISTS idx_rack_master_store_num ON rack_master(store, rack_number);

-- ============================================
-- 2. rack_history: 랙별 변경 이력
-- ============================================
CREATE TABLE IF NOT EXISTS rack_history (
    id BIGSERIAL PRIMARY KEY,
    store TEXT NOT NULL,
    rack_name TEXT NOT NULL,
    rack_number INTEGER NOT NULL,
    products JSONB NOT NULL DEFAULT '[]',
    product_count INTEGER NOT NULL DEFAULT 0,
    changes JSONB NOT NULL DEFAULT '{}',
    scanned_at TEXT NOT NULL
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_rack_history_store ON rack_history(store);
CREATE INDEX IF NOT EXISTS idx_rack_history_store_name ON rack_history(store, rack_name);
CREATE INDEX IF NOT EXISTS idx_rack_history_scanned ON rack_history(scanned_at DESC);
CREATE INDEX IF NOT EXISTS idx_rack_history_store_scanned ON rack_history(store, scanned_at DESC);
