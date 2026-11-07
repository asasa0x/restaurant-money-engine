import unittest
from unittest.mock import patch, MagicMock
from backend.app import app
from backend.services.money_engine import calculate_recipe_cost, simulate_profit_impact

class TestPhase3Integration(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_calculate_recipe_cost(self):
        # 1. Multiple ingredients calculation
        # Beef Patty: 0.200 kg * 15.00 = 3.00
        # Brioche Bun: 1.000 portion * 0.85 = 0.85
        # Truffle Mayo: 0.030 kg * 25.00 = 0.75
        # Aged Cheddar: 0.050 kg * 12.00 = 0.60
        # Total expected: 3.00 + 0.85 + 0.75 + 0.60 = 5.20
        ingredients = [
            {"ingredient_name": "Beef Patty", "quantity": 0.200, "unit": "kg", "unit_cost": 15.00},
            {"ingredient_name": "Brioche Bun", "quantity": 1.000, "unit": "portion", "unit_cost": 0.85},
            {"ingredient_name": "Truffle Mayo", "quantity": 0.030, "unit": "kg", "unit_cost": 25.00},
            {"ingredient_name": "Aged Cheddar", "quantity": 0.050, "unit": "kg", "unit_cost": 12.00}
        ]
        total_cost = calculate_recipe_cost(ingredients)
        self.assertEqual(total_cost, 5.20)

        # 2. Empty list returns 0.0
        self.assertEqual(calculate_recipe_cost([]), 0.0)

    def test_simulate_profit_impact_math(self):
        baseline = {
            "gross_sales": 100000.0,
            "cogs": 30000.0,
            "labor_cost": 30000.0
        }
        # Baseline: Prime Cost = 60,000 (60%), Prime Margin = 40,000 (40%)
        
        # Scenario: 5% menu price increase, 4% ingredient inflation, 2% labor adjustment
        sim = simulate_profit_impact(
            current_financials=baseline,
            ingredient_inflation_pct=4.0,
            price_change_pct=5.0,
            labor_change_pct=2.0
        )
        
        # Projected Sales: 100,000 * 1.05 = 105,000
        self.assertEqual(sim["projected"]["gross_sales"], 105000.0)
        # Projected COGS: 30,000 * 1.04 = 31,200
        self.assertEqual(sim["projected"]["cogs"], 31200.0)
        # Projected Labor: 30,000 * 1.02 = 30,600
        self.assertEqual(sim["projected"]["labor_cost"], 30600.0)
        # Projected Prime Cost: 31,200 + 30,600 = 61,800
        self.assertEqual(sim["projected"]["prime_cost"], 61800.0)
        # Projected Margin: 105,000 - 61,800 = 43,200
        self.assertEqual(sim["projected"]["prime_margin"], 43200.0)
        # Margin Delta: 43,200 - 40,000 = +3,200 (Gain)
        self.assertEqual(sim["impact"]["margin_delta"], 3200.0)
        self.assertTrue(sim["impact"]["is_gain"])

    def test_menu_and_simulation_unauthorized(self):
        # 1. Menu endpoints return 401 without auth
        res_menu_get = self.client.get("/api/v1/menu/")
        self.assertEqual(res_menu_get.status_code, 401)

        res_menu_post = self.client.post("/api/v1/menu/", json={"name": "Pasta", "selling_price": 20.0})
        self.assertEqual(res_menu_post.status_code, 401)

        res_recipe_post = self.client.post("/api/v1/menu/test-id/recipe", json={"ingredients": []})
        self.assertEqual(res_recipe_post.status_code, 401)

        # 2. Simulation endpoint returns 401 without auth
        res_sim = self.client.post("/api/v1/simulation/run", json={"price_change_pct": 5.0})
        self.assertEqual(res_sim.status_code, 401)

    @patch("backend.services.supabase_client.supabase.auth.get_user")
    @patch("backend.services.supabase_client.supabase.table")
    def test_menu_crud_authenticated(self, mock_table, mock_get_user):
        mock_user = MagicMock()
        mock_user.id = "usr_tenant_owner"
        mock_auth_res = MagicMock()
        mock_auth_res.user = mock_user
        mock_get_user.return_value = mock_auth_res

        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.single.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.insert.return_value = mock_query
        mock_query.update.return_value = mock_query
        mock_query.delete.return_value = mock_query

        current_table = {"name": ""}
        def fake_table(name):
            current_table["name"] = name
            return mock_query
        mock_table.side_effect = fake_table

        def fake_execute():
            res = MagicMock()
            if current_table["name"] == "profiles":
                res.data = {"restaurant_id": "rest_uuid_999", "role": "owner"}
            elif current_table["name"] == "menu_items":
                res.data = [{
                    "id": "item_uuid_101",
                    "restaurant_id": "rest_uuid_999",
                    "name": "Dry-Aged Ribeye",
                    "category": "Mains",
                    "selling_price": 45.0,
                    "price": 45.0,
                    "cost_price": 14.5,
                    "cost": 14.5,
                    "is_active": True
                }]
            else:
                res.data = []
            return res
        mock_query.execute.side_effect = fake_execute

        headers = {"Authorization": "Bearer valid_jwt_token"}

        # 1. List menu items
        get_res = self.client.get("/api/v1/menu/", headers=headers)
        self.assertEqual(get_res.status_code, 200)
        get_data = get_res.get_json()
        self.assertTrue(get_data["success"])
        self.assertEqual(get_data["restaurant_id"], "rest_uuid_999")
        self.assertEqual(len(get_data["data"]), 1)
        self.assertEqual(get_data["data"][0]["unit_margin"], 30.5)

        # 2. Create menu item
        post_res = self.client.post(
            "/api/v1/menu/",
            headers=headers,
            json={"name": "Dry-Aged Ribeye", "selling_price": 45.0, "cost_price": 14.5, "category": "Mains"}
        )
        self.assertEqual(post_res.status_code, 201)
        self.assertTrue(post_res.get_json()["success"])

        # 3. Update menu item
        put_res = self.client.put(
            "/api/v1/menu/item_uuid_101",
            headers=headers,
            json={"selling_price": 48.0}
        )
        self.assertEqual(put_res.status_code, 200)

        # 4. Soft delete menu item
        del_res = self.client.delete("/api/v1/menu/item_uuid_101", headers=headers)
        self.assertEqual(del_res.status_code, 200)

    @patch("backend.services.supabase_client.supabase.auth.get_user")
    @patch("backend.services.supabase_client.supabase.table")
    def test_recipe_upsert_and_auto_costing(self, mock_table, mock_get_user):
        mock_user = MagicMock()
        mock_user.id = "usr_chef"
        mock_auth_res = MagicMock()
        mock_auth_res.user = mock_user
        mock_get_user.return_value = mock_auth_res

        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.single.return_value = mock_query
        mock_query.insert.return_value = mock_query
        mock_query.update.return_value = mock_query
        mock_query.delete.return_value = mock_query

        current_table = {"name": ""}
        def fake_table(name):
            current_table["name"] = name
            return mock_query
        mock_table.side_effect = fake_table

        def fake_execute():
            res = MagicMock()
            if current_table["name"] == "profiles":
                res.data = {"restaurant_id": "rest_uuid_999", "role": "owner"}
            elif current_table["name"] == "menu_items":
                res.data = [{"id": "item_123", "name": "Gourmet Burger", "selling_price": 18.0, "cost_price": 5.20}]
            elif current_table["name"] == "recipes":
                res.data = [
                    {"ingredient_name": "Beef", "quantity": 0.2, "unit": "kg", "unit_cost": 15.0},
                    {"ingredient_name": "Bun", "quantity": 1.0, "unit": "portion", "unit_cost": 0.85}
                ]
            else:
                res.data = []
            return res
        mock_query.execute.side_effect = fake_execute

        headers = {"Authorization": "Bearer valid_jwt_token"}

        # Upsert recipe ingredients:
        # Beef: 0.2 * 15.0 = 3.00, Bun: 1.0 * 0.85 = 0.85 -> Total = 3.85
        recipe_payload = {
            "ingredients": [
                {"ingredient_name": "Beef Patty", "quantity": 0.200, "unit": "kg", "unit_cost": 15.00},
                {"ingredient_name": "Brioche Bun", "quantity": 1.000, "unit": "portion", "unit_cost": 0.85}
            ]
        }
        res = self.client.post("/api/v1/menu/item_123/recipe", headers=headers, json=recipe_payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["calculated_cost_price"], 3.85)
        self.assertEqual(data["menu_item_id"], "item_123")

    @patch("backend.services.supabase_client.supabase.auth.get_user")
    @patch("backend.services.supabase_client.supabase.table")
    def test_simulation_endpoint(self, mock_table, mock_get_user):
        mock_user = MagicMock()
        mock_user.id = "usr_manager"
        mock_auth_res = MagicMock()
        mock_auth_res.user = mock_user
        mock_get_user.return_value = mock_auth_res

        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.single.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.limit.return_value = mock_query

        current_table = {"name": ""}
        def fake_table(name):
            current_table["name"] = name
            return mock_query
        mock_table.side_effect = fake_table

        def fake_execute():
            res = MagicMock()
            if current_table["name"] == "profiles":
                res.data = {"restaurant_id": "rest_uuid_999", "role": "owner"}
            elif current_table["name"] == "daily_financials":
                res.data = [
                    {"gross_sales": 30000.0, "cogs": 9000.0, "labor_cost": 9000.0},
                    {"gross_sales": 20000.0, "cogs": 6000.0, "labor_cost": 6000.0}
                ]
            else:
                res.data = []
            return res
        mock_query.execute.side_effect = fake_execute

        headers = {"Authorization": "Bearer valid_jwt_token"}

        # Run simulation with 5% price raise, 3% inflation, 2% labor increase
        payload = {
            "price_change_pct": 5.0,
            "ingredient_inflation_pct": 3.0,
            "labor_change_pct": 2.0
        }
        res = self.client.post("/api/v1/simulation/run", headers=headers, json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("simulation", data)
        self.assertIn("baseline", data["simulation"])
        self.assertIn("projected", data["simulation"])
        self.assertIn("impact", data["simulation"])

        # Baseline: Sales=50000, COGS=15000, Labor=15000 -> Prime Cost=30000 (60%)
        self.assertEqual(data["simulation"]["baseline"]["gross_sales"], 50000.0)
        self.assertEqual(data["simulation"]["baseline"]["prime_cost"], 30000.0)
        # Projected Sales: 50000 * 1.05 = 52500
        self.assertEqual(data["simulation"]["projected"]["gross_sales"], 52500.0)
        # Profit impact is positive gain
        self.assertTrue(data["simulation"]["impact"]["is_gain"])

if __name__ == "__main__":
    unittest.main()
