-- Migration: Add company_id to risk tables for multi-tenant isolation
-- Date: 2026-03-30
-- Purpose: Associate risk data with companies so each org sees only its own portfolio
--
-- IMPORTANT: Run this in Supabase SQL Editor
-- Before running, find sergio's company_id:
--   SELECT company_id FROM xerenity.user_profiles WHERE email = 'sergiohr40@gmail.com';

-- ============================================================
-- 1. risk_futures_portfolio — posiciones individuales de futuros
-- ============================================================

ALTER TABLE xerenity.risk_futures_portfolio
    ADD COLUMN IF NOT EXISTS company_id UUID REFERENCES trading.company(id);

-- Migrate existing data to sergio's company
-- Replace '<SERGIO_COMPANY_ID>' with actual UUID from query above
-- UPDATE xerenity.risk_futures_portfolio SET company_id = '<SERGIO_COMPANY_ID>' WHERE company_id IS NULL;

-- After migration, make NOT NULL
-- ALTER TABLE xerenity.risk_futures_portfolio ALTER COLUMN company_id SET NOT NULL;

-- Update unique constraint to be per-company
ALTER TABLE xerenity.risk_futures_portfolio DROP CONSTRAINT IF EXISTS uq_futures_position;
ALTER TABLE xerenity.risk_futures_portfolio
    ADD CONSTRAINT uq_futures_position
    UNIQUE (company_id, asset, contract, entry_date, direction);

-- Index for company-scoped queries
CREATE INDEX IF NOT EXISTS idx_futures_portfolio_company
    ON xerenity.risk_futures_portfolio (company_id, active);

-- ============================================================
-- 2. risk_positions — posiciones benchmark y GR (agregadas)
-- ============================================================

ALTER TABLE xerenity.risk_positions
    ADD COLUMN IF NOT EXISTS company_id UUID REFERENCES trading.company(id);

-- UPDATE xerenity.risk_positions SET company_id = '<SERGIO_COMPANY_ID>' WHERE company_id IS NULL;
-- ALTER TABLE xerenity.risk_positions ALTER COLUMN company_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_risk_positions_company
    ON xerenity.risk_positions (company_id);

-- ============================================================
-- 3. risk_portfolio_config — configuracion del portafolio
-- ============================================================

ALTER TABLE xerenity.risk_portfolio_config
    ADD COLUMN IF NOT EXISTS company_id UUID REFERENCES trading.company(id);

-- UPDATE xerenity.risk_portfolio_config SET company_id = '<SERGIO_COMPANY_ID>' WHERE company_id IS NULL;
-- ALTER TABLE xerenity.risk_portfolio_config ALTER COLUMN company_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_risk_portfolio_config_company
    ON xerenity.risk_portfolio_config (company_id);

-- ============================================================
-- 4. Permisos (ya deben existir, pero por si acaso)
-- ============================================================

GRANT USAGE ON SCHEMA xerenity TO anon, authenticated, service_role;
GRANT ALL ON xerenity.risk_futures_portfolio TO anon, authenticated, service_role;
GRANT ALL ON xerenity.risk_positions TO anon, authenticated, service_role;
GRANT ALL ON xerenity.risk_portfolio_config TO anon, authenticated, service_role;

-- ============================================================
-- NOTE: risk_prices NO se modifica — son datos de mercado globales
-- ============================================================
