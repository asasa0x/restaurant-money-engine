-- Supabase PostgreSQL Migration: Recipes & Ingredient Costing
-- Extension: UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Create recipes table (Bill of Materials per Menu Item)
CREATE TABLE IF NOT EXISTS recipes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    menu_item_id UUID NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
    ingredient_name VARCHAR(255) NOT NULL,
    quantity NUMERIC(10, 3) NOT NULL CHECK (quantity > 0),
    unit VARCHAR(50) NOT NULL, -- e.g., kg, g, l, ml, oz, portion
    unit_cost NUMERIC(10, 2) NOT NULL CHECK (unit_cost >= 0),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for foreign key performance
CREATE INDEX IF NOT EXISTS idx_recipes_menu_item_id ON recipes(menu_item_id);

-- 2. Enable Row Level Security (RLS)
ALTER TABLE recipes ENABLE ROW LEVEL SECURITY;

-- 3. Tenant Isolation Policy via menu_items.restaurant_id
-- Restricts recipe access so users only interact with recipes belonging to their tenant restaurant
CREATE POLICY tenant_isolation_recipes_policy ON recipes
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM menu_items m
            JOIN profiles p ON p.restaurant_id = m.restaurant_id
            WHERE m.id = recipes.menu_item_id
              AND p.id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM menu_items m
            JOIN profiles p ON p.restaurant_id = m.restaurant_id
            WHERE m.id = recipes.menu_item_id
              AND p.id = auth.uid()
        )
    );

