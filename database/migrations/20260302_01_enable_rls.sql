-- Migration: Enable Row Level Security on all tables
-- Date: 2026-03-02
-- Purpose: Protect against direct Supabase REST API / client SDK access.
--          The backend on Render connects as the `postgres` role (table owner),
--          which bypasses RLS by default, so application queries are unaffected.

BEGIN;

-- ============================================================================
-- Helper: extract Clerk user ID from Supabase JWT
-- Supabase sets request.jwt.claims from the JWT payload; Clerk puts the user
-- ID in the "sub" claim.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.clerk_user_id() RETURNS text
    LANGUAGE sql STABLE
    AS $$
  SELECT coalesce(
    nullif(current_setting('request.jwt.claims', true), '')::json ->> 'sub',
    ''
  );
$$;

-- ============================================================================
-- 1. Tables with owner_user_id — full CRUD scoped to the owning user
-- ============================================================================

-- portfolios
ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;
CREATE POLICY portfolios_owner ON portfolios
    USING (owner_user_id = public.clerk_user_id())
    WITH CHECK (owner_user_id = public.clerk_user_id());

-- transactions
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY transactions_owner ON transactions
    USING (owner_user_id = public.clerk_user_id())
    WITH CHECK (owner_user_id = public.clerk_user_id());

-- portfolio_target_allocations
ALTER TABLE portfolio_target_allocations ENABLE ROW LEVEL SECURITY;
CREATE POLICY portfolio_target_allocations_owner ON portfolio_target_allocations
    USING (owner_user_id = public.clerk_user_id())
    WITH CHECK (owner_user_id = public.clerk_user_id());

-- csv_import_batches
ALTER TABLE csv_import_batches ENABLE ROW LEVEL SECURITY;
CREATE POLICY csv_import_batches_owner ON csv_import_batches
    USING (owner_user_id = public.clerk_user_id())
    WITH CHECK (owner_user_id = public.clerk_user_id());

-- pac_rules
ALTER TABLE pac_rules ENABLE ROW LEVEL SECURITY;
CREATE POLICY pac_rules_owner ON pac_rules
    USING (owner_user_id = public.clerk_user_id())
    WITH CHECK (owner_user_id = public.clerk_user_id());

-- api_idempotency_keys
ALTER TABLE api_idempotency_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY api_idempotency_keys_owner ON api_idempotency_keys
    USING (owner_user_id = public.clerk_user_id())
    WITH CHECK (owner_user_id = public.clerk_user_id());

-- ============================================================================
-- 2. app_user_settings — uses "user_id" instead of "owner_user_id"
-- ============================================================================

ALTER TABLE app_user_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY app_user_settings_owner ON app_user_settings
    USING (user_id = public.clerk_user_id())
    WITH CHECK (user_id = public.clerk_user_id());

-- ============================================================================
-- 3. pac_executions — FK to pac_rules, scoped via join
-- ============================================================================

ALTER TABLE pac_executions ENABLE ROW LEVEL SECURITY;
CREATE POLICY pac_executions_owner ON pac_executions
    USING (
        EXISTS (
            SELECT 1 FROM pac_rules
            WHERE pac_rules.id = pac_executions.pac_rule_id
              AND pac_rules.owner_user_id = public.clerk_user_id()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM pac_rules
            WHERE pac_rules.id = pac_executions.pac_rule_id
              AND pac_rules.owner_user_id = public.clerk_user_id()
        )
    );

-- ============================================================================
-- 4. Shared / system tables — SELECT for all authenticated, mutations only
--    for service_role (which maps to the postgres/service_role user).
-- ============================================================================

-- assets
ALTER TABLE assets ENABLE ROW LEVEL SECURITY;
CREATE POLICY assets_select ON assets FOR SELECT
    USING (public.clerk_user_id() <> '');
CREATE POLICY assets_mutation ON assets FOR ALL
    USING (current_setting('role') = 'service_role');

-- asset_provider_symbols
ALTER TABLE asset_provider_symbols ENABLE ROW LEVEL SECURITY;
CREATE POLICY asset_provider_symbols_select ON asset_provider_symbols FOR SELECT
    USING (public.clerk_user_id() <> '');
CREATE POLICY asset_provider_symbols_mutation ON asset_provider_symbols FOR ALL
    USING (current_setting('role') = 'service_role');

-- price_ticks
ALTER TABLE price_ticks ENABLE ROW LEVEL SECURITY;
CREATE POLICY price_ticks_select ON price_ticks FOR SELECT
    USING (public.clerk_user_id() <> '');
CREATE POLICY price_ticks_mutation ON price_ticks FOR ALL
    USING (current_setting('role') = 'service_role');

-- price_bars_1m
ALTER TABLE price_bars_1m ENABLE ROW LEVEL SECURITY;
CREATE POLICY price_bars_1m_select ON price_bars_1m FOR SELECT
    USING (public.clerk_user_id() <> '');
CREATE POLICY price_bars_1m_mutation ON price_bars_1m FOR ALL
    USING (current_setting('role') = 'service_role');

-- price_bars_1d
ALTER TABLE price_bars_1d ENABLE ROW LEVEL SECURITY;
CREATE POLICY price_bars_1d_select ON price_bars_1d FOR SELECT
    USING (public.clerk_user_id() <> '');
CREATE POLICY price_bars_1d_mutation ON price_bars_1d FOR ALL
    USING (current_setting('role') = 'service_role');

-- fx_rates_1d
ALTER TABLE fx_rates_1d ENABLE ROW LEVEL SECURITY;
CREATE POLICY fx_rates_1d_select ON fx_rates_1d FOR SELECT
    USING (public.clerk_user_id() <> '');
CREATE POLICY fx_rates_1d_mutation ON fx_rates_1d FOR ALL
    USING (current_setting('role') = 'service_role');

COMMIT;
