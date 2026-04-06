-- Migration v2: Super admin access via owner → user_profiles JOIN
-- Date: 2026-04-06
--
-- CORRECCIÓN: Las tablas de posiciones NO tienen company_id.
-- Resolvemos la empresa a través de: position.owner → user_profiles.company_id
--
-- Lógica:
--   super_admin → ve posiciones de todos los usuarios de la empresa seleccionada
--   corp_admin  → ve posiciones de todos los usuarios de su empresa
--   otros       → solo sus propias posiciones (sin cambios)
--
-- IMPORTANT: Run in Supabase SQL Editor
-- IMPORTANT: Drop old overloaded functions first to avoid signature conflicts

-- ============================================================
-- 0. Limpiar funciones anteriores con firma (p_company_id uuid)
--    para evitar conflictos de overload
-- ============================================================

DROP FUNCTION IF EXISTS xerenity.get_xccy_positions(uuid);
DROP FUNCTION IF EXISTS xerenity.get_ndf_positions(uuid);
DROP FUNCTION IF EXISTS xerenity.get_ibr_swap_positions(uuid);
DROP FUNCTION IF EXISTS xerenity.get_loans(text[], uuid);

-- También limpiamos las versiones originales sin parámetros
DROP FUNCTION IF EXISTS xerenity.get_xccy_positions();
DROP FUNCTION IF EXISTS xerenity.get_ndf_positions();
DROP FUNCTION IF EXISTS xerenity.get_ibr_swap_positions();
DROP FUNCTION IF EXISTS xerenity.get_loans(text[]);

-- ============================================================
-- Helper: obtener role y company_id del usuario actual
-- ============================================================

CREATE OR REPLACE FUNCTION xerenity.get_caller_context()
RETURNS TABLE(caller_role text, caller_company_id uuid)
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
BEGIN
    RETURN QUERY
    SELECT up.role, up.company_id
    FROM xerenity.user_profiles up
    WHERE up.id = auth.uid()
    LIMIT 1;
END;
$$;

GRANT EXECUTE ON FUNCTION xerenity.get_caller_context() TO authenticated;

-- ============================================================
-- 1. XCCY Positions
-- ============================================================

CREATE OR REPLACE FUNCTION xerenity.get_xccy_positions(p_company_id uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    positions_data jsonb;
    v_role text;
    v_company_id uuid;
BEGIN
    IF auth.uid() IS NULL THEN
        PERFORM set_config('response.status', '401', TRUE);
        RETURN json_build_object('message', 'User must be logged in');
    END IF;

    SELECT caller_role, caller_company_id INTO v_role, v_company_id
    FROM xerenity.get_caller_context();

    IF v_role = 'super_admin' THEN
        IF p_company_id IS NOT NULL THEN
            -- Super admin: see positions of users in the specified company
            SELECT jsonb_agg(row_to_json(p)) INTO positions_data
            FROM trading.xccy_position p
            JOIN xerenity.user_profiles up ON up.id = p.owner
            WHERE up.company_id = p_company_id
            ORDER BY p.created_at DESC;
        ELSE
            -- Super admin without company filter: see all
            SELECT jsonb_agg(row_to_json(p)) INTO positions_data
            FROM trading.xccy_position p
            ORDER BY p.created_at DESC;
        END IF;
    ELSIF v_role = 'corp_admin' THEN
        -- Corp admin: see positions of all users in their company
        SELECT jsonb_agg(row_to_json(p)) INTO positions_data
        FROM trading.xccy_position p
        JOIN xerenity.user_profiles up ON up.id = p.owner
        WHERE up.company_id = v_company_id
        ORDER BY p.created_at DESC;
    ELSE
        -- Others: see only their own positions
        SELECT jsonb_agg(row_to_json(p)) INTO positions_data
        FROM trading.xccy_position p
        WHERE p.owner = auth.uid()
        ORDER BY p.created_at DESC;
    END IF;

    PERFORM set_config('response.status', '200', TRUE);
    RETURN COALESCE(positions_data, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION xerenity.get_xccy_positions(uuid) TO authenticated;

-- ============================================================
-- 2. NDF Positions
-- ============================================================

CREATE OR REPLACE FUNCTION xerenity.get_ndf_positions(p_company_id uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    positions_data jsonb;
    v_role text;
    v_company_id uuid;
BEGIN
    IF auth.uid() IS NULL THEN
        PERFORM set_config('response.status', '401', TRUE);
        RETURN json_build_object('message', 'User must be logged in');
    END IF;

    SELECT caller_role, caller_company_id INTO v_role, v_company_id
    FROM xerenity.get_caller_context();

    IF v_role = 'super_admin' THEN
        IF p_company_id IS NOT NULL THEN
            SELECT jsonb_agg(row_to_json(p)) INTO positions_data
            FROM trading.ndf_position p
            JOIN xerenity.user_profiles up ON up.id = p.owner
            WHERE up.company_id = p_company_id
            ORDER BY p.created_at DESC;
        ELSE
            SELECT jsonb_agg(row_to_json(p)) INTO positions_data
            FROM trading.ndf_position p
            ORDER BY p.created_at DESC;
        END IF;
    ELSIF v_role = 'corp_admin' THEN
        SELECT jsonb_agg(row_to_json(p)) INTO positions_data
        FROM trading.ndf_position p
        JOIN xerenity.user_profiles up ON up.id = p.owner
        WHERE up.company_id = v_company_id
        ORDER BY p.created_at DESC;
    ELSE
        SELECT jsonb_agg(row_to_json(p)) INTO positions_data
        FROM trading.ndf_position p
        WHERE p.owner = auth.uid()
        ORDER BY p.created_at DESC;
    END IF;

    PERFORM set_config('response.status', '200', TRUE);
    RETURN COALESCE(positions_data, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION xerenity.get_ndf_positions(uuid) TO authenticated;

-- ============================================================
-- 3. IBR Swap Positions
-- ============================================================

CREATE OR REPLACE FUNCTION xerenity.get_ibr_swap_positions(p_company_id uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    positions_data jsonb;
    v_role text;
    v_company_id uuid;
BEGIN
    IF auth.uid() IS NULL THEN
        PERFORM set_config('response.status', '401', TRUE);
        RETURN json_build_object('message', 'User must be logged in');
    END IF;

    SELECT caller_role, caller_company_id INTO v_role, v_company_id
    FROM xerenity.get_caller_context();

    IF v_role = 'super_admin' THEN
        IF p_company_id IS NOT NULL THEN
            SELECT jsonb_agg(row_to_json(p)) INTO positions_data
            FROM trading.ibr_swap_position p
            JOIN xerenity.user_profiles up ON up.id = p.owner
            WHERE up.company_id = p_company_id
            ORDER BY p.created_at DESC;
        ELSE
            SELECT jsonb_agg(row_to_json(p)) INTO positions_data
            FROM trading.ibr_swap_position p
            ORDER BY p.created_at DESC;
        END IF;
    ELSIF v_role = 'corp_admin' THEN
        SELECT jsonb_agg(row_to_json(p)) INTO positions_data
        FROM trading.ibr_swap_position p
        JOIN xerenity.user_profiles up ON up.id = p.owner
        WHERE up.company_id = v_company_id
        ORDER BY p.created_at DESC;
    ELSE
        SELECT jsonb_agg(row_to_json(p)) INTO positions_data
        FROM trading.ibr_swap_position p
        WHERE p.owner = auth.uid()
        ORDER BY p.created_at DESC;
    END IF;

    PERFORM set_config('response.status', '200', TRUE);
    RETURN COALESCE(positions_data, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION xerenity.get_ibr_swap_positions(uuid) TO authenticated;

-- ============================================================
-- 4. Loans — resolve company via owner → user_profiles
-- ============================================================

CREATE OR REPLACE FUNCTION xerenity.get_loans(bank_name_filter TEXT[] DEFAULT NULL, p_company_id uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    loans_data jsonb;
    v_role text;
    v_company_id uuid;
BEGIN
    IF auth.uid() IS NULL THEN
        PERFORM set_config('response.status', '401', TRUE);
        RETURN json_build_object('message', 'User must be logged in');
    END IF;

    SELECT caller_role, caller_company_id INTO v_role, v_company_id
    FROM xerenity.get_caller_context();

    IF v_role = 'super_admin' THEN
        IF p_company_id IS NOT NULL THEN
            SELECT jsonb_agg(loan_search) INTO loans_data FROM (
                SELECT l.* FROM loans.loan l
                JOIN xerenity.user_profiles up ON up.id = l.owner
                WHERE up.company_id = p_company_id
                AND (bank_name_filter IS NULL OR l.bank = ANY(bank_name_filter))
                ORDER BY l.id
            ) AS loan_search;
        ELSE
            SELECT jsonb_agg(loan_search) INTO loans_data FROM (
                SELECT * FROM loans.loan
                WHERE bank_name_filter IS NULL OR bank = ANY(bank_name_filter)
                ORDER BY id
            ) AS loan_search;
        END IF;
    ELSIF v_role = 'corp_admin' THEN
        SELECT jsonb_agg(loan_search) INTO loans_data FROM (
            SELECT l.* FROM loans.loan l
            JOIN xerenity.user_profiles up ON up.id = l.owner
            WHERE up.company_id = v_company_id
            AND (bank_name_filter IS NULL OR l.bank = ANY(bank_name_filter))
            ORDER BY l.id
        ) AS loan_search;
    ELSE
        IF bank_name_filter IS NULL THEN
            SELECT jsonb_agg(loan_search) INTO loans_data FROM (
                SELECT * FROM loans.loan WHERE owner = auth.uid()
            ) AS loan_search;
        ELSE
            SELECT jsonb_agg(loan_search) INTO loans_data FROM (
                SELECT * FROM loans.loan WHERE owner = auth.uid() AND bank = ANY(bank_name_filter)
            ) AS loan_search;
        END IF;
    END IF;

    PERFORM set_config('response.status', '200', TRUE);
    RETURN COALESCE(loans_data, '[]');
END;
$$;

GRANT EXECUTE ON FUNCTION xerenity.get_loans(text[], uuid) TO authenticated;
