-- ============================================================================
-- Migration 002: Recipes & Ingredient Costing Schema
-- Target: Supabase PostgreSQL (Postgres 14+)
-- Table: recipes (Bill of Materials linked to menu_items)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.recipes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    menu_item_id UUID NOT NULL REFERENCES public.menu_items(id) ON DELETE CASCADE,
    ingredient_name VARCHAR(255) NOT NULL,
    quantity NUMERIC(10, 3) NOT NULL CHECK (quantity > 0),
    unit VARCHAR(50) NOT NULL, -- e.g., kg, g, l, ml, oz, portion
    unit_cost NUMERIC(10, 2) NOT NULL CHECK (unit_cost >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index on foreign key for recipe component queries
CREATE INDEX IF NOT EXISTS idx_recipes_menu_item_id ON public.recipes(menu_item_id);

-- Trigger to update updated_at timestamp
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

