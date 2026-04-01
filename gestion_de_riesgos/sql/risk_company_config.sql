-- Table: risk_company_config
-- Per-company configuration for the risk management module.
-- Each company defines which commodities it manages, contract specs, and exposure parameters.
--
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS xerenity.risk_company_config (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    company_id      UUID NOT NULL REFERENCES trading.company(id) UNIQUE,

    -- Commodities this company monitors (dynamic asset list)
    -- Example: [{"asset":"MAIZ","unit":"TONS","price_unit":"cents/bu","contract_multiplier":5000,"chart_color":"#f59e0b","exchange":"CME","symbol":"ZC"}, ...]
    commodities     JSONB NOT NULL DEFAULT '[]',

    -- Currency exposure asset (always present in addition to commodities)
    currency_asset  TEXT NOT NULL DEFAULT 'USD',
    currency_unit   TEXT NOT NULL DEFAULT 'USD/COP',

    -- Default exposure parameters per commodity (company-specific conversion factors)
    exposure_defaults JSONB DEFAULT '{}',

    -- VaR configuration
    rolling_window  INTEGER DEFAULT 180,
    confidence_level NUMERIC DEFAULT 0.99,

    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Permissions
GRANT USAGE ON SCHEMA xerenity TO anon, authenticated, service_role;
GRANT ALL ON xerenity.risk_company_config TO anon, authenticated, service_role;

-- Index
CREATE INDEX IF NOT EXISTS idx_risk_company_config_company
    ON xerenity.risk_company_config (company_id);

COMMENT ON TABLE xerenity.risk_company_config IS
    'Per-company configuration for risk management: commodities, contract specs, exposure parameters, VaR settings.';

-- ============================================================
-- Seed: Super de Alimentos
-- ============================================================

INSERT INTO xerenity.risk_company_config (company_id, commodities, exposure_defaults)
VALUES (
    'e8516f19-7286-4e04-a63e-24ca9364d807',
    '[
        {"asset": "MAIZ", "unit": "TONS", "price_unit": "cents/bu", "contract_multiplier": 5000, "chart_color": "#f59e0b", "exchange": "CME", "symbol": "ZC"},
        {"asset": "AZUCAR", "unit": "TONS", "price_unit": "cents/lb", "contract_multiplier": 112000, "chart_color": "#10b981", "exchange": "ICE", "symbol": "SB"},
        {"asset": "CACAO", "unit": "TONS", "price_unit": "USD/ton", "contract_multiplier": 10, "chart_color": "#8b5cf6", "exchange": "ICE", "symbol": "CC"}
    ]',
    '{
        "azucar": {"libras_contrato": 112000, "lbs_per_ton": 2204.62, "factor_crudo_refinado": 1.05},
        "maiz": {"conv_bu_ton": 0.3936825, "credito_pct": 0.26, "factor_maiz_glucosa": 1.495},
        "cacao": {"ton_contrato": 10, "derivados": [
            {"nombre": "COCOA_POLVO", "factor": 1.22},
            {"nombre": "MANTECA_CACAO", "factor": 1.95},
            {"nombre": "LICOR_CACAO", "factor": 1.53}
        ]}
    }'
)
ON CONFLICT (company_id) DO UPDATE SET
    commodities = EXCLUDED.commodities,
    exposure_defaults = EXCLUDED.exposure_defaults,
    updated_at = now();
