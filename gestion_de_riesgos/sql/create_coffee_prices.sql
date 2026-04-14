-- ============================================================================
-- xerenity.coffee_prices
-- Precios de cafe colectados desde FNC, Anserma y Manizales
-- ============================================================================

CREATE TABLE IF NOT EXISTS xerenity.coffee_prices (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fecha       DATE NOT NULL,
    fuente      TEXT NOT NULL
                CHECK (fuente IN ('FNC', 'ANSERMA', 'MANIZALES')),
    tipo_precio TEXT NOT NULL
                CHECK (tipo_precio IN (
                    'precio_interno_carga',
                    'precio_ref_f94',
                    'precio_base_f90',
                    'precio_nespresso_f90',
                    'precio_cp_creciente_f90',
                    'precio_humedo_cereza',
                    'precio_base'
                )),
    valor       NUMERIC NOT NULL,
    unidad      TEXT NOT NULL DEFAULT 'COP',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_coffee_prices_fecha_fuente_tipo
        UNIQUE (fecha, fuente, tipo_precio)
);

CREATE INDEX IF NOT EXISTS idx_coffee_prices_fecha
    ON xerenity.coffee_prices (fecha DESC);
CREATE INDEX IF NOT EXISTS idx_coffee_prices_fuente_tipo
    ON xerenity.coffee_prices (fuente, tipo_precio);

-- ----------------------------------------------------------------------------
-- Role 'collector' (crear si no existe)
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'collector') THEN
        CREATE ROLE collector NOLOGIN;
    END IF;
END$$;

-- ----------------------------------------------------------------------------
-- GRANTs (schema + tabla)
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA xerenity TO anon, authenticated, collector;

GRANT SELECT                 ON xerenity.coffee_prices TO anon;
GRANT SELECT                 ON xerenity.coffee_prices TO authenticated;
GRANT SELECT, INSERT, UPDATE ON xerenity.coffee_prices TO collector;

-- ----------------------------------------------------------------------------
-- RLS
-- ----------------------------------------------------------------------------
ALTER TABLE xerenity.coffee_prices ENABLE ROW LEVEL SECURITY;

-- collector: lectura
CREATE POLICY coffee_prices_collector_select
    ON xerenity.coffee_prices
    FOR SELECT
    TO collector
    USING (true);

-- collector: insert
CREATE POLICY coffee_prices_collector_insert
    ON xerenity.coffee_prices
    FOR INSERT
    TO collector
    WITH CHECK (true);

-- collector: update (para upsert idempotente)
CREATE POLICY coffee_prices_collector_update
    ON xerenity.coffee_prices
    FOR UPDATE
    TO collector
    USING (true)
    WITH CHECK (true);

-- authenticated: solo lectura
CREATE POLICY coffee_prices_authenticated_select
    ON xerenity.coffee_prices
    FOR SELECT
    TO authenticated
    USING (true);
