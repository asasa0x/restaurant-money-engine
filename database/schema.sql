-- ============================================================================
-- Restaurant Money Engine: Complete Supabase PostgreSQL Schema
-- Idempotent full deployment script for Postgres 14+ / Supabase
-- Includes:
--   - Extensions (uuid-ossp, pgcrypto)
--   - Tables: restaurants, profiles, menu_items, daily_financials, item_sales_logs, recipes
--   - Foreign Keys with CASCADE, Check Constraints, Defaults, Unique Constraints
--   - Performance Indexes
--   - Price synchronization triggers
--   - Row Level Security (RLS) policies for complete multi-tenant data isolation
-- ============================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ----------------------------------------------------------------------------
-- 1. Table: restaurants (Root Tenant Entity)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.restaurants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_restaurants_name ON public.restaurants(name);

-- ----------------------------------------------------------------------------
-- 2. Table: profiles (User Profile & Tenant Mapping)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    restaurant_id UUID REFERENCES public.restaurants(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'manager', 'member')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_profiles_restaurant_id ON public.profiles(restaurant_id);

-- ----------------------------------------------------------------------------
-- 3. Table: menu_items (Tenant Menu Catalog & Pricing)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.menu_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES public.restaurants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL DEFAULT 'General',
    selling_price NUMERIC(10, 2) NOT NULL CHECK (selling_price >= 0),
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    cost_price NUMERIC(10, 2) NOT NULL DEFAULT 0.0 CHECK (cost_price >= 0),
    cost NUMERIC(10, 2) NOT NULL DEFAULT 0.0 CHECK (cost >= 0),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_menu_items_restaurant_id ON public.menu_items(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_menu_items_restaurant_active ON public.menu_items(restaurant_id, is_active);
CREATE INDEX IF NOT EXISTS idx_menu_items_category ON public.menu_items(restaurant_id, category);

-- Trigger Function: Keep selling_price/price and cost_price/cost in sync
CREATE OR REPLACE FUNCTION public.sync_menu_item_prices()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.selling_price IS NOT NULL AND (NEW.price IS NULL OR NEW.price <> NEW.selling_price) THEN
        NEW.price := NEW.selling_price;
    ELSIF NEW.price IS NOT NULL AND (NEW.selling_price IS NULL OR NEW.selling_price <> NEW.price) THEN
        NEW.selling_price := NEW.price;
    END IF;

    IF NEW.cost_price IS NOT NULL AND (NEW.cost IS NULL OR NEW.cost <> NEW.cost_price) THEN
        NEW.cost := NEW.cost_price;
    ELSIF NEW.cost IS NOT NULL AND (NEW.cost_price IS NULL OR NEW.cost_price <> NEW.cost) THEN
        NEW.cost_price := NEW.cost;
    END IF;

    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_menu_item_prices ON public.menu_items;
CREATE TRIGGER trg_sync_menu_item_prices
BEFORE INSERT OR UPDATE ON public.menu_items
FOR EACH ROW EXECUTE FUNCTION public.sync_menu_item_prices();

-- ----------------------------------------------------------------------------
-- 4. Table: daily_financials (Daily KPIs & Financial Summaries)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.daily_financials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES public.restaurants(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    gross_sales NUMERIC(12, 2) NOT NULL CHECK (gross_sales >= 0),
    cogs NUMERIC(12, 2) NOT NULL CHECK (cogs >= 0),
    labor_cost NUMERIC(12, 2) NOT NULL CHECK (labor_cost >= 0),
    prime_cost NUMERIC(12, 2) NOT NULL CHECK (prime_cost >= 0),
    prime_cost_pct NUMERIC(6, 2) CHECK (prime_cost_pct IS NULL OR prime_cost_pct >= 0),
    status VARCHAR(20) NOT NULL CHECK (status IN ('HEALTHY', 'ALERT', 'NO_DATA')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_daily_financials_restaurant_date UNIQUE(restaurant_id, date)
);

CREATE INDEX IF NOT EXISTS idx_daily_financials_restaurant_date ON public.daily_financials(restaurant_id, date DESC);

-- ----------------------------------------------------------------------------
-- 5. Table: item_sales_logs (Historical Item Sales for Matrix Calculations)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.item_sales_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES public.restaurants(id) ON DELETE CASCADE,
    item_id UUID NOT NULL REFERENCES public.menu_items(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    sale_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_item_sales_logs_restaurant_item ON public.item_sales_logs(restaurant_id, item_id);
CREATE INDEX IF NOT EXISTS idx_item_sales_logs_restaurant_date ON public.item_sales_logs(restaurant_id, sale_date DESC);

-- ----------------------------------------------------------------------------
-- 6. Table: recipes (Bill of Materials linked to menu_items)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.recipes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    menu_item_id UUID NOT NULL REFERENCES public.menu_items(id) ON DELETE CASCADE,
    ingredient_name VARCHAR(255) NOT NULL,
    quantity NUMERIC(10, 3) NOT NULL CHECK (quantity > 0),
    unit VARCHAR(50) NOT NULL,
    unit_cost NUMERIC(10, 2) NOT NULL CHECK (unit_cost >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recipes_menu_item_id ON public.recipes(menu_item_id);

CREATE OR REPLACE FUNCTION public.update_recipe_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_recipe_timestamp ON public.recipes;
CREATE TRIGGER trg_update_recipe_timestamp
BEFORE UPDATE ON public.recipes
FOR EACH ROW EXECUTE FUNCTION public.update_recipe_timestamp();

-- ----------------------------------------------------------------------------
-- 7. Row Level Security (RLS) & Helper Function
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.current_restaurant_id()
RETURNS UUID AS $$
    SELECT restaurant_id FROM public.profiles WHERE id = auth.uid() LIMIT 1;
$$ LANGUAGE sql STABLE SECURITY DEFINER;

ALTER TABLE public.restaurants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.menu_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_financials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.item_sales_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recipes ENABLE ROW LEVEL SECURITY;

-- Restaurants Policies
DROP POLICY IF EXISTS tenant_select_restaurants ON public.restaurants;
CREATE POLICY tenant_select_restaurants ON public.restaurants
    FOR SELECT USING (id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_update_restaurants ON public.restaurants;
CREATE POLICY tenant_update_restaurants ON public.restaurants
    FOR UPDATE USING (
        id = public.current_restaurant_id()
        AND EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid()
              AND profiles.restaurant_id = restaurants.id
              AND profiles.role IN ('owner', 'admin')
        )
    );

-- Profiles Policies
DROP POLICY IF EXISTS tenant_select_profiles ON public.profiles;
CREATE POLICY tenant_select_profiles ON public.profiles
    FOR SELECT USING (id = auth.uid() OR restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_insert_profiles ON public.profiles;
CREATE POLICY tenant_insert_profiles ON public.profiles
    FOR INSERT WITH CHECK (id = auth.uid());

DROP POLICY IF EXISTS tenant_update_profiles ON public.profiles;
CREATE POLICY tenant_update_profiles ON public.profiles
    FOR UPDATE USING (id = auth.uid()) WITH CHECK (id = auth.uid());

-- Menu Items Policies
DROP POLICY IF EXISTS tenant_select_menu_items ON public.menu_items;
CREATE POLICY tenant_select_menu_items ON public.menu_items
    FOR SELECT USING (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_insert_menu_items ON public.menu_items;
CREATE POLICY tenant_insert_menu_items ON public.menu_items
    FOR INSERT WITH CHECK (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_update_menu_items ON public.menu_items;
CREATE POLICY tenant_update_menu_items ON public.menu_items
    FOR UPDATE USING (restaurant_id = public.current_restaurant_id())
    WITH CHECK (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_delete_menu_items ON public.menu_items;
CREATE POLICY tenant_delete_menu_items ON public.menu_items
    FOR DELETE USING (restaurant_id = public.current_restaurant_id());

-- Daily Financials Policies
DROP POLICY IF EXISTS tenant_select_daily_financials ON public.daily_financials;
CREATE POLICY tenant_select_daily_financials ON public.daily_financials
    FOR SELECT USING (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_insert_daily_financials ON public.daily_financials;
CREATE POLICY tenant_insert_daily_financials ON public.daily_financials
    FOR INSERT WITH CHECK (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_update_daily_financials ON public.daily_financials;
CREATE POLICY tenant_update_daily_financials ON public.daily_financials
    FOR UPDATE USING (restaurant_id = public.current_restaurant_id())
    WITH CHECK (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_delete_daily_financials ON public.daily_financials;
CREATE POLICY tenant_delete_daily_financials ON public.daily_financials
    FOR DELETE USING (restaurant_id = public.current_restaurant_id());

-- Item Sales Logs Policies
DROP POLICY IF EXISTS tenant_select_item_sales_logs ON public.item_sales_logs;
CREATE POLICY tenant_select_item_sales_logs ON public.item_sales_logs
    FOR SELECT USING (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_insert_item_sales_logs ON public.item_sales_logs;
CREATE POLICY tenant_insert_item_sales_logs ON public.item_sales_logs
    FOR INSERT WITH CHECK (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_update_item_sales_logs ON public.item_sales_logs;
CREATE POLICY tenant_update_item_sales_logs ON public.item_sales_logs
    FOR UPDATE USING (restaurant_id = public.current_restaurant_id())
    WITH CHECK (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_delete_item_sales_logs ON public.item_sales_logs;
CREATE POLICY tenant_delete_item_sales_logs ON public.item_sales_logs
    FOR DELETE USING (restaurant_id = public.current_restaurant_id());

-- Recipes Policies
DROP POLICY IF EXISTS tenant_select_recipes ON public.recipes;
CREATE POLICY tenant_select_recipes ON public.recipes
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.menu_items m
            WHERE m.id = recipes.menu_item_id
              AND m.restaurant_id = public.current_restaurant_id()
        )
    );

DROP POLICY IF EXISTS tenant_insert_recipes ON public.recipes;
CREATE POLICY tenant_insert_recipes ON public.recipes
    FOR INSERT WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.menu_items m
            WHERE m.id = recipes.menu_item_id
              AND m.restaurant_id = public.current_restaurant_id()
        )
    );

DROP POLICY IF EXISTS tenant_update_recipes ON public.recipes;
CREATE POLICY tenant_update_recipes ON public.recipes
    FOR UPDATE USING (
        EXISTS (
            SELECT 1 FROM public.menu_items m
            WHERE m.id = recipes.menu_item_id
              AND m.restaurant_id = public.current_restaurant_id()
        )
    ) WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.menu_items m
            WHERE m.id = recipes.menu_item_id
              AND m.restaurant_id = public.current_restaurant_id()
        )
    );

DROP POLICY IF EXISTS tenant_delete_recipes ON public.recipes;
CREATE POLICY tenant_delete_recipes ON public.recipes
    FOR DELETE USING (
        EXISTS (
            SELECT 1 FROM public.menu_items m
            WHERE m.id = recipes.menu_item_id
              AND m.restaurant_id = public.current_restaurant_id()
        )
    );

