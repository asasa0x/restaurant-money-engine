-- ============================================================================
-- Migration 004: Customer QR Orders (orders + order_items)
-- Target: Supabase PostgreSQL (Postgres 14+)
-- Customers place orders through the public QR menu page. Orders are written by
-- the backend (service role) after server-side price verification; restaurant
-- staff read/update them through RLS-protected, tenant-scoped access.
-- Run AFTER 001, 002 and 003.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES public.restaurants(id) ON DELETE CASCADE,
    table_number VARCHAR(30),
    customer_name VARCHAR(100) NOT NULL,
    customer_phone VARCHAR(30),
    notes VARCHAR(500),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'preparing', 'ready', 'completed', 'cancelled')),
    subtotal NUMERIC(12, 2) NOT NULL CHECK (subtotal >= 0),
    total NUMERIC(12, 2) NOT NULL CHECK (total >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.order_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
    restaurant_id UUID NOT NULL REFERENCES public.restaurants(id) ON DELETE CASCADE,
    menu_item_id UUID REFERENCES public.menu_items(id) ON DELETE SET NULL,
    item_name VARCHAR(255) NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 99),
    line_total NUMERIC(12, 2) NOT NULL CHECK (line_total >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_restaurant_created ON public.orders(restaurant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_restaurant_status ON public.orders(restaurant_id, status);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON public.order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_restaurant_id ON public.order_items(restaurant_id);

-- Keep orders.updated_at current
CREATE OR REPLACE FUNCTION public.update_order_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_order_timestamp ON public.orders;
CREATE TRIGGER trg_update_order_timestamp
BEFORE UPDATE ON public.orders
FOR EACH ROW EXECUTE FUNCTION public.update_order_timestamp();

-- ----------------------------------------------------------------------------
-- Row Level Security: tenant staff only. There is intentionally NO anonymous
-- INSERT policy: public ordering goes through the backend API (service role).
-- ----------------------------------------------------------------------------
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_items ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_select_orders ON public.orders;
CREATE POLICY tenant_select_orders ON public.orders
    FOR SELECT
    USING (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_update_orders ON public.orders;
CREATE POLICY tenant_update_orders ON public.orders
    FOR UPDATE
    USING (restaurant_id = public.current_restaurant_id())
    WITH CHECK (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_delete_orders ON public.orders;
CREATE POLICY tenant_delete_orders ON public.orders
    FOR DELETE
    USING (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_select_order_items ON public.order_items;
CREATE POLICY tenant_select_order_items ON public.order_items
    FOR SELECT
    USING (restaurant_id = public.current_restaurant_id());

DROP POLICY IF EXISTS tenant_delete_order_items ON public.order_items;
CREATE POLICY tenant_delete_order_items ON public.order_items
    FOR DELETE
    USING (restaurant_id = public.current_restaurant_id());
