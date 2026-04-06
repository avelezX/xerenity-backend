-- Migration: Add super_admin access to all portfolio RPCs
-- Date: 2026-04-06
-- Purpose: Allow super_admin to view positions from any company
--
-- Logic:
--   - super_admin: sees positions of ALL users in the specified company (or all if no company)
--   - corp_admin: sees positions of ALL users in their own company
--   - others: see only their own positions (unchanged behavior)
--
-- IMPORTANT: Run in Supabase SQL Editor

-- ============================================================
-- Helper: get current user's role and company_id
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
-- 1. XCCY Positions — with super_admin/corp_admin access
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
        -- Super admin: see all positions, or filter by company if specified
        IF p_company_id IS NOT NULL THEN
            SELECT jsonb_agg(row_to_json(p)) INTO positions_data
            FROM trading.xccy_position p
            WHERE p.company_id = p_company_id
            ORDER BY p.created_at DESC;
        ELSE
            SELECT jsonb_agg(row_to_json(p)) INTO positions_data
            FROM trading.xccy_position p
            ORDER BY p.created_at DESC;
        END IF;
    ELSIF v_role = 'corp_admin' THEN
        -- Corp admin: see all positions in their company
        SELECT jsonb_agg(row_to_json(p)) INTO positions_data
        FROM trading.xccy_position p
        WHERE p.company_id = v_company_id
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
-- 2. NDF Positions — with super_admin/corp_admin access
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
            WHERE p.company_id = p_company_id
            ORDER BY p.created_at DESC;
        ELSE
            SELECT jsonb_agg(row_to_json(p)) INTO positions_data
            FROM trading.ndf_position p
            ORDER BY p.created_at DESC;
        END IF;
    ELSIF v_role = 'corp_admin' THEN
        SELECT jsonb_agg(row_to_json(p)) INTO positions_data
        FROM trading.ndf_position p
        WHERE p.company_id = v_company_id
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
-- 3. IBR Swap Positions — with super_admin/corp_admin access
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
            WHERE p.company_id = p_company_id
            ORDER BY p.created_at DESC;
        ELSE
            SELECT jsonb_agg(row_to_json(p)) INTO positions_data
            FROM trading.ibr_swap_position p
            ORDER BY p.created_at DESC;
        END IF;
    ELSIF v_role = 'corp_admin' THEN
        SELECT jsonb_agg(row_to_json(p)) INTO positions_data
        FROM trading.ibr_swap_position p
        WHERE p.company_id = v_company_id
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
-- 4. Loans — with super_admin/corp_admin access
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
        -- Super admin: see loans of all users in the specified company (or all)
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
        -- Corp admin: see loans of all users in their company
        SELECT jsonb_agg(loan_search) INTO loans_data FROM (
            SELECT l.* FROM loans.loan l
            JOIN xerenity.user_profiles up ON up.id = l.owner
            WHERE up.company_id = v_company_id
            AND (bank_name_filter IS NULL OR l.bank = ANY(bank_name_filter))
            ORDER BY l.id
        ) AS loan_search;
    ELSE
        -- Others: see only their own loans
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

GRANT EXECUTE ON FUNCTION xerenity.get_loans(TEXT[], uuid) TO authenticated;

-- ============================================================
-- NOTE: The old function signatures (without p_company_id) still work
-- because PostgreSQL supports function overloading. The default NULL
-- parameter means existing callers don't need to change.
-- ============================================================
