-- Fix: xerenity.create_company ahora inserta en AMBAS tablas
-- (xerenity.companies + trading.company) para que los FKs de las tablas
-- de riesgo (risk_company_config, risk_futures_portfolio, etc) no fallen
-- con 409 foreign key violation.
--
-- Problema: las tablas de risk usan FK a trading.company, pero
-- create_company solo insertaba en xerenity.companies. Al crear una
-- empresa nueva y luego guardar su risk_company_config, PostgREST
-- retornaba 409 porque el company_id no existia en trading.company.
--
-- Aplicado en Supabase SQL Editor: abril 2026

-- 1. Fix para El Embrujo (ya existia en xerenity.companies, faltaba en trading.company)
INSERT INTO trading.company (id, name)
VALUES ('a16a0193-5d0c-4e44-9a90-7f6231faddf3', 'El Embrujo')
ON CONFLICT (id) DO NOTHING;

-- 2. Actualizar create_company para insertar en ambas tablas en futuras creaciones
CREATE OR REPLACE FUNCTION xerenity.create_company(p_name text, p_nit text DEFAULT NULL)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = xerenity
AS $$
DECLARE
  caller_role text;
  new_id uuid;
BEGIN
  SELECT role INTO caller_role FROM xerenity.user_profiles WHERE id = auth.uid();
  IF caller_role != 'super_admin' THEN
    RAISE EXCEPTION 'Forbidden: requires super_admin role';
  END IF;

  -- Crear en xerenity.companies y capturar el id
  INSERT INTO xerenity.companies (name, nit)
  VALUES (p_name, p_nit)
  RETURNING id INTO new_id;

  -- Espejo en trading.company con el MISMO id (para que las FKs de risk funcionen)
  INSERT INTO trading.company (id, name)
  VALUES (new_id, p_name)
  ON CONFLICT (id) DO NOTHING;

  RETURN new_id;
END;
$$;

GRANT EXECUTE ON FUNCTION xerenity.create_company(text, text) TO authenticated;

-- 3. Verificacion
-- SELECT 'xerenity.companies' AS tabla, id, name FROM xerenity.companies WHERE name ILIKE '%embrujo%'
-- UNION ALL
-- SELECT 'trading.company', id, name FROM trading.company WHERE name ILIKE '%embrujo%';
-- Debe retornar 2 filas con el mismo UUID.
