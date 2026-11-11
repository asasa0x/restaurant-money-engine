-- ============================================================================
-- Migration 001: Core Multi-Tenant Schema
-- Target: Supabase PostgreSQL (Postgres 14+)
-- Tables: restaurants, profiles, menu_items, daily_financials, item_sales_logs
-- ============================================================================

-- Required Extensions
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

-- Index on restaurant name for searching/filtering
CREATE INDEX IF NOT EXISTS idx_restaurants_name ON public.restaurants(name);

-- ----------------------------------------------------------------------------
-- 2. Table: profiles (User Profile & Tenant Membership)
-- References auth.users(id) in Supabase Auth
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    restaurant_id UUID REFERENCES public.restaurants(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'manager', 'member')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for tenant lookup from user profile
CREATE INDEX IF NOT EXISTS idx_profiles_restaurant_id ON public.profiles(restaurant_id);

-- ----------------------------------------------------------------------------
-- 3. Table: menu_items (Tenant Menu Catalog & Pricing)
-- Supports both (selling_price, cost_price) and legacy (price, cost) columns
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

-- Indexes for tenant catalog queries and active items
CREATE INDEX IF NOT EXISTS idx_menu_items_restaurant_id ON public.menu_items(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_menu_items_restaurant_active ON public.menu_items(restaurant_id, is_active);
CREATE INDEX IF NOT EXISTS idx_menu_items_category ON public.menu_items(restaurant_id, category);

-- Trigger Function: Synchronize selling_price <-> price and cost_price <-> cost
CREATE OR REPLACE FUNCTION public.sync_menu_item_prices()
RETURNS TRIGGER AS $$
BEGIN
    -- Sync selling price
    IF NEW.selling_price IS NOT NULL AND (NEW.price IS NULL OR NEW.price <> NEW.selling_price) THEN
        NEW.price := NEW.selling_price;
    ELSIF NEW.price IS NOT NULL AND (NEW.selling_price IS NULL OR NEW.selling_price <> NEW.price) THEN
        NEW.selling_price := NEW.price;
    END IF;

    -- Sync cost price
    IF NEW.cost_price IS NOT NULL AND (NEW.cost IS NULL OR NEW.cost <> NEW.cost_price) THEN
        NEW.cost := NEW.cost_price;
    ELSIF NEW.cost IS NOT NULL AND (NEW.cost_price IS NULL OR NEW.cost_price <> NEW.cost) THEN
        NEW.cost_price := NEW.cost;
    END IF;

    -- Update timestamp
    NEW.updated_at := NOW();

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_menu_item_prices ON public.menu_items;
CREATE TRIGGER trg_sync_menu_item_prices
BEFORE INSERT OR UPDATE ON public.menu_items
FOR EACH ROW EXECUTE FUNCTION public.sync_menu_item_prices();

-- ----------------------------------------------------------------------------
-- 4. Table: daily_financials (Daily Sales, COGS, Labor, and Prime Cost KPIs)
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

-- Index for ordering by date within tenant
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

-- Indexes for item aggregation and date range lookups
CREATE INDEX IF NOT EXISTS idx_item_sales_logs_restaurant_item ON public.item_sales_logs(restaurant_id, item_id);
CREATE INDEX IF NOT EXISTS idx_item_sales_logs_restaurant_date ON public.item_sales_logs(restaurant_id, sale_date DESC);

