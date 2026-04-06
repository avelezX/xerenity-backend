-- Tabla con precios historicos de TODOS los contratos de futuros
-- (no solo el front contract). Necesaria para mark-to-market
-- del Portafolio GR cuando hay multiples contratos abiertos.
--
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS xerenity.risk_prices_all_contracts (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    date        DATE NOT NULL,
    asset       TEXT NOT NULL,
    contract    TEXT NOT NULL,
    open        NUMERIC,
    high        NUMERIC,
    low         NUMERIC,
    close       NUMERIC NOT NULL,
    volume      INTEGER,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (date, asset, contract)
);

CREATE INDEX IF NOT EXISTS idx_risk_prices_all_asset_contract
    ON xerenity.risk_prices_all_contracts (asset, contract);

CREATE INDEX IF NOT EXISTS idx_risk_prices_all_date
    ON xerenity.risk_prices_all_contracts (date DESC);

GRANT USAGE ON SCHEMA xerenity TO anon, authenticated, service_role;
GRANT ALL ON xerenity.risk_prices_all_contracts TO anon, authenticated, service_role;

COMMENT ON TABLE xerenity.risk_prices_all_contracts IS
    'Precios historicos de TODOS los contratos de futuros (no solo el front). Para mark-to-market del Portafolio GR.';
