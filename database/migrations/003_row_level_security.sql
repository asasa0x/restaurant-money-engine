-- ============================================================================
-- Migration 003: Row Level Security (RLS) & Multi-Tenant Isolation
-- Target: Supabase PostgreSQL (Postgres 14+)
-- Tables Secured: restaurants, profiles, menu_items, daily_financials, item_sales_logs, recipes
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Helper Function: Current User's Restaurant ID
-- Extracts restaurant_id from public.profiles for auth.uid()
-- SECURITY DEFINER allows safe read of tenant mapping without recursion
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.current_restaurant_id()
RETURNS UUID AS $$
    SELECT restaurant_id FROM public.profiles WHERE id = auth.uid() LIMIT 1;
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- ----------------------------------------------------------------------------
-- 2. Enable Row Level Security on all 6 tables
-- ----------------------------------------------------------------------------
ALTER TABLE public.restaurants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.menu_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_financials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.item_sales_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recipes ENABLE ROW LEVEL SECURITY;

-- ----------------------------------------------------------------------------
-- 3. RLS Policies: restaurants
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS tenant_select_restaurants ON public.restaurants;
CREATE POLICY tenant_select_restaurants ON public.restaurants
    FOR SELECT
    USING (id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_update_restaurants ON public.restaurants;
CREATE POLICY tenant_update_restaurants ON public.restaurants
    FOR UPDATE
    USING (
        id = public.current_restaurant_id()
        AND EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid()
              AND profiles.restaurant_id = restaurants.id
              AND profiles.role IN ('owner', 'admin')
        )
    );

-- ----------------------------------------------------------------------------
-- 4. RLS Policies: profiles
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS tenant_select_profiles ON public.profiles;
CREATE POLICY tenant_select_profiles ON public.profiles
    FOR SELECT
    USING (
        id = auth.uid()
        OR restaurant_id = public.current_restaurant_id()
    );

DROP POLICY IF EXISTS tenant_insert_profiles ON public.profiles;
CREATE POLICY tenant_insert_profiles ON public.profiles
    FOR INSERT
    WITH CHECK (id = auth.uid());

DROP POLICY IF EXISTS tenant_update_profiles ON public.profiles;
CREATE POLICY tenant_update_profiles ON public.profiles
    FOR UPDATE
    USING (id = auth.uid())
    WITH CHECK (id = auth.uid());

-- ----------------------------------------------------------------------------
-- 5. RLS Policies: menu_items
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS tenant_select_menu_items ON public.menu_items;
CREATE POLICY tenant_select_menu_items ON public.menu_items
    FOR SELECT
    USING (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_insert_menu_items ON public.menu_items;
CREATE POLICY tenant_insert_menu_items ON public.menu_items
    FOR INSERT
    WITH CHECK (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_update_menu_items ON public.menu_items;
CREATE POLICY tenant_update_menu_items ON public.menu_items
    FOR UPDATE
    USING (restaurant_id = public.current_restaurant_id())
    WITH CHECK (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_delete_menu_items ON public.menu_items;
CREATE POLICY tenant_delete_menu_items ON public.menu_items
    FOR DELETE
    USING (restaurant_id = public.current_restaurant_id());

-- ----------------------------------------------------------------------------
-- 6. RLS Policies: daily_financials
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS tenant_select_daily_financials ON public.daily_financials;
CREATE POLICY tenant_select_daily_financials ON public.daily_financials
    FOR SELECT
    USING (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_insert_daily_financials ON public.daily_financials;
CREATE POLICY tenant_insert_daily_financials ON public.daily_financials
    FOR INSERT
    WITH CHECK (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_update_daily_financials ON public.daily_financials;
CREATE POLICY tenant_update_daily_financials ON public.daily_financials
    FOR UPDATE
    USING (restaurant_id = public.current_restaurant_id())
    WITH CHECK (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_delete_daily_financials ON public.daily_financials;
CREATE POLICY tenant_delete_daily_financials ON public.daily_financials
    FOR DELETE
    USING (restaurant_id = public.current_restaurant_id());

-- ----------------------------------------------------------------------------
-- 7. RLS Policies: item_sales_logs
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS tenant_select_item_sales_logs ON public.item_sales_logs;
CREATE POLICY tenant_select_item_sales_logs ON public.item_sales_logs
    FOR SELECT
    USING (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_insert_item_sales_logs ON public.item_sales_logs;
CREATE POLICY tenant_insert_item_sales_logs ON public.item_sales_logs
    FOR INSERT
    WITH CHECK (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_update_item_sales_logs ON public.item_sales_logs;
CREATE POLICY tenant_update_item_sales_logs ON public.item_sales_logs
    FOR UPDATE
    USING (restaurant_id = public.current_restaurant_id())
    WITH CHECK (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_delete_item_sales_logs ON public.item_sales_logs;
CREATE POLICY tenant_delete_item_sales_logs ON public.item_sales_logs
    FOR DELETE
    USING (restaurant_id = public.current_restaurant_id());

-- ----------------------------------------------------------------------------
-- 8. RLS Policies: recipes (Via menu_items.restaurant_id)
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS tenant_select_recipes ON public.recipes;
CREATE POLICY tenant_select_recipes ON public.recipes
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.menu_items m
            WHERE m.id = recipes.menu_item_id
              AND m.restaurant_id = public.current_restaurant_id()
        )
    );

DROP POLICY IF EXISTS tenant_insert_recipes ON public.recipes;
CREATE POLICY tenant_insert_recipes ON public.recipes
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.menu_items m
            WHERE m.id = recipes.menu_item_id
              AND m.restaurant_id = public.current_restaurant_id()
        )
    );

DROP POLICY IF EXISTS tenant_update_recipes ON public.recipes;
CREATE POLICY tenant_update_recipes ON public.recipes
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM public.menu_items m
            WHERE m.id = recipes.menu_item_id
              AND m.restaurant_id = public.current_restaurant_id()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.menu_items m
            WHERE m.id = recipes.menu_item_id
              AND m.restaurant_id = public.current_restaurant_id()
        )
    );

DROP POLICY IF EXISTS tenant_delete_recipes ON public.recipes;
CREATE POLICY tenant_delete_recipes ON public.recipes
    FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM public.menu_items m
            WHERE m.id = recipes.menu_item_id
              AND m.restaurant_id = public.current_restaurant_id()
        )
    );

