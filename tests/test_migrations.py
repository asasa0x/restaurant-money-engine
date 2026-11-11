"""
Tests for Phase 2 Supabase PostgreSQL Migrations.
Validates table schemas, UUID relationships, constraints, indexes,
Row Level Security policies, and demo seed data UUID compliance.
"""

import unittest
import re
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = BASE_DIR / "database" / "migrations"
SCHEMA_FILE = BASE_DIR / "database" / "schema.sql"

REQUIRED_TABLES = [
    "restaurants",
    "profiles",
    "menu_items",
    "daily_financials",
    "item_sales_logs",
    "recipes"
]

class TestDatabaseMigrations(unittest.TestCase):

    def setUp(self):
        self.mig_001 = (MIGRATIONS_DIR / "001_core_schema.sql").read_text(encoding="utf-8")
        self.mig_002 = (MIGRATIONS_DIR / "002_recipes.sql").read_text(encoding="utf-8")
        self.mig_003 = (MIGRATIONS_DIR / "003_row_level_security.sql").read_text(encoding="utf-8")
        self.full_schema = SCHEMA_FILE.read_text(encoding="utf-8")

    def test_migration_files_exist(self):
        """Verify all ordered migration files and unified schema exist."""
        self.assertTrue((MIGRATIONS_DIR / "001_core_schema.sql").is_file())
        self.assertTrue((MIGRATIONS_DIR / "002_recipes.sql").is_file())
        self.assertTrue((MIGRATIONS_DIR / "003_row_level_security.sql").is_file())
        self.assertTrue(SCHEMA_FILE.is_file())

    def test_all_six_tables_defined_with_uuid_pks(self):
        """Verify all required tables are created with UUID primary keys."""
        combined_sql = self.mig_001 + "\n" + self.mig_002

        for table in REQUIRED_TABLES:
            with self.subTest(table=table):
                # Check CREATE TABLE statement
                pattern = rf"CREATE TABLE (?:IF NOT EXISTS )?(?:public\.)?{table}\s*\("
                self.assertRegex(combined_sql, pattern, f"Missing CREATE TABLE for {table}")

                # Check UUID PRIMARY KEY
                pk_pattern = rf"id UUID PRIMARY KEY"
                self.assertIn(pk_pattern, combined_sql, f"Table {table} must define an id UUID PRIMARY KEY")

    def test_foreign_key_relationships_and_cascades(self):
        """Verify foreign key relationships with ON DELETE CASCADE."""
        combined_sql = self.mig_001 + "\n" + self.mig_002

        expected_fks = [
            ("profiles", r"restaurant_id UUID REFERENCES (?:public\.)?restaurants\(id\) ON DELETE CASCADE"),
            ("profiles", r"id UUID PRIMARY KEY REFERENCES auth\.users\(id\) ON DELETE CASCADE"),
            ("menu_items", r"restaurant_id UUID NOT NULL REFERENCES (?:public\.)?restaurants\(id\) ON DELETE CASCADE"),
            ("daily_financials", r"restaurant_id UUID NOT NULL REFERENCES (?:public\.)?restaurants\(id\) ON DELETE CASCADE"),
            ("item_sales_logs", r"restaurant_id UUID NOT NULL REFERENCES (?:public\.)?restaurants\(id\) ON DELETE CASCADE"),
            ("item_sales_logs", r"item_id UUID NOT NULL REFERENCES (?:public\.)?menu_items\(id\) ON DELETE CASCADE"),
            ("recipes", r"menu_item_id UUID NOT NULL REFERENCES (?:public\.)?menu_items\(id\) ON DELETE CASCADE"),
        ]

        for table, fk_regex in expected_fks:
            with self.subTest(table=table, fk=fk_regex):
                self.assertRegex(
                    combined_sql,
                    fk_regex,
                    f"Table {table} missing expected foreign key constraint: {fk_regex}"
                )

    def test_check_constraints_and_validations(self):
        """Verify essential CHECK constraints and UNIQUE constraints."""
        combined_sql = self.mig_001 + "\n" + self.mig_002

        # Menu items price constraints
        self.assertIn("selling_price NUMERIC(10, 2) NOT NULL CHECK (selling_price >= 0)", combined_sql)
        self.assertIn("cost_price NUMERIC(10, 2) NOT NULL DEFAULT 0.0 CHECK (cost_price >= 0)", combined_sql)

        # Daily financials checks and unique constraint
        self.assertIn("gross_sales NUMERIC(12, 2) NOT NULL CHECK (gross_sales >= 0)", combined_sql)
        self.assertIn("cogs NUMERIC(12, 2) NOT NULL CHECK (cogs >= 0)", combined_sql)
        self.assertIn("labor_cost NUMERIC(12, 2) NOT NULL CHECK (labor_cost >= 0)", combined_sql)
        self.assertIn("status VARCHAR(20) NOT NULL CHECK (status IN ('HEALTHY', 'ALERT', 'NO_DATA'))", combined_sql)
        self.assertRegex(combined_sql, r"UNIQUE\s*\(\s*restaurant_id\s*,\s*date\s*\)")

        # Recipes quantity and cost checks
        self.assertIn("quantity NUMERIC(10, 3) NOT NULL CHECK (quantity > 0)", combined_sql)
        self.assertIn("unit_cost NUMERIC(10, 2) NOT NULL CHECK (unit_cost >= 0)", combined_sql)

        # Profiles role validation
        self.assertRegex(combined_sql, r"role VARCHAR\(50\).+CHECK \(role IN \('owner', 'admin', 'manager', 'member'\)\)")

    def test_performance_indexes(self):
        """Verify performance indexes on foreign keys and tenant filtering columns."""
        combined_sql = self.mig_001 + "\n" + self.mig_002

        expected_indexes = [
            "idx_profiles_restaurant_id",
            "idx_menu_items_restaurant_id",
            "idx_menu_items_restaurant_active",
            "idx_daily_financials_restaurant_date",
            "idx_item_sales_logs_restaurant_item",
            "idx_item_sales_logs_restaurant_date",
            "idx_recipes_menu_item_id",
        ]

        for idx in expected_indexes:
            with self.subTest(index=idx):
                self.assertIn(idx, combined_sql, f"Missing index {idx}")

    def test_menu_item_price_synchronization_trigger(self):
        """Verify trigger exists to synchronize selling_price/price and cost_price/cost."""
        self.assertIn("FUNCTION public.sync_menu_item_prices()", self.mig_001)
        self.assertIn("TRIGGER trg_sync_menu_item_prices", self.mig_001)
        self.assertIn("BEFORE INSERT OR UPDATE ON public.menu_items", self.mig_001)

    def test_rls_enabled_on_all_tables(self):
        """Verify Row Level Security is explicitly enabled on all 6 tables."""
        for table in REQUIRED_TABLES:
            with self.subTest(table=table):
                pattern = rf"ALTER TABLE (?:public\.)?{table} ENABLE ROW LEVEL SECURITY;"
                self.assertRegex(self.mig_003, pattern, f"RLS not enabled on {table} in 003_row_level_security.sql")
                self.assertRegex(self.full_schema, pattern, f"RLS not enabled on {table} in schema.sql")

    def test_tenant_isolation_helper_function(self):
        """Verify current_restaurant_id() helper function is defined with SECURITY DEFINER."""
        pattern = r"CREATE OR REPLACE FUNCTION public\.current_restaurant_id\(\)\s*RETURNS UUID AS"
        self.assertRegex(self.mig_003, pattern)
        self.assertIn("SECURITY DEFINER", self.mig_003)
        self.assertIn("SELECT restaurant_id FROM public.profiles WHERE id = auth.uid()", self.mig_003)

    def test_rls_policies_defined_for_all_tables(self):
        """Verify tenant isolation policies for all tenant tables."""
        # Check menu_items policies
        self.assertIn("tenant_select_menu_items", self.mig_003)
        self.assertIn("tenant_insert_menu_items", self.mig_003)
        self.assertIn("tenant_update_menu_items", self.mig_003)
        self.assertIn("tenant_delete_menu_items", self.mig_003)

        # Check daily_financials policies
        self.assertIn("tenant_select_daily_financials", self.mig_003)
        self.assertIn("tenant_insert_daily_financials", self.mig_003)
        self.assertIn("tenant_update_daily_financials", self.mig_003)
        self.assertIn("tenant_delete_daily_financials", self.mig_003)

        # Check recipes policies (joined via menu_items)
        self.assertIn("tenant_select_recipes", self.mig_003)
        self.assertIn("tenant_insert_recipes", self.mig_003)
        self.assertIn("tenant_update_recipes", self.mig_003)
        self.assertIn("tenant_delete_recipes", self.mig_003)
        self.assertIn("m.restaurant_id = public.current_restaurant_id()", self.mig_003)

    def test_full_schema_matches_individual_migrations(self):
        """Verify schema.sql contains all definitions present in 001, 002, and 003."""
        for table in REQUIRED_TABLES:
            self.assertIn(f"TABLE IF NOT EXISTS public.{table}", self.full_schema)

        self.assertIn("sync_menu_item_prices()", self.full_schema)
        self.assertIn("update_recipe_timestamp()", self.full_schema)
        self.assertIn("current_restaurant_id()", self.full_schema)

    def test_seed_demo_data_uses_valid_uuids(self):
        """Verify that seed_demo_data.py uses strictly valid UUIDs matching PostgreSQL schema."""
        from database.seed_demo_data import (
            DEMO_RESTAURANT_ID,
            DEMO_MENU_ITEMS,
            DEMO_RECIPES,
            DEMO_SALES_LOGS
        )

        # Validate restaurant ID
        try:
            val = uuid.UUID(DEMO_RESTAURANT_ID)
            self.assertEqual(str(val), DEMO_RESTAURANT_ID)
        except ValueError:
            self.fail(f"DEMO_RESTAURANT_ID '{DEMO_RESTAURANT_ID}' is not a valid UUID")

        # Validate menu item IDs
        item_ids = set()
        for item in DEMO_MENU_ITEMS:
            try:
                val = uuid.UUID(item["id"])
                self.assertEqual(str(val), item["id"])
                item_ids.add(item["id"])
            except ValueError:
                self.fail(f"Menu item ID '{item['id']}' is not a valid UUID")

        # Validate recipe foreign keys
        for rec in DEMO_RECIPES:
            self.assertIn(
                rec["menu_item_id"],
                item_ids,
                f"Recipe refers to non-existent menu_item_id: {rec['menu_item_id']}"
            )

        # Validate sales log foreign keys
        for log in DEMO_SALES_LOGS:
            self.assertEqual(log["restaurant_id"], DEMO_RESTAURANT_ID)
            self.assertIn(
                log["item_id"],
                item_ids,
                f"Sales log refers to non-existent item_id: {log['item_id']}"
            )


if __name__ == "__main__":
    unittest.main()

