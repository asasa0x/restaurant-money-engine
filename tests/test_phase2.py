import unittest
from unittest.mock import patch, MagicMock
from backend.app import app
from backend.services.money_engine import calculate_prime_cost, calculate_menu_matrix

class TestPhase2Integration(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_prime_cost_healthy_and_alert(self):
        # 1. Healthy prime cost (<= 60%)
        healthy = calculate_prime_cost(cogs=2000, labor_cost=1500, gross_sales=6000)
        self.assertEqual(healthy["status"], "HEALTHY")
        self.assertEqual(healthy["prime_cost"], 3500.0)
        self.assertAlmostEqual(healthy["prime_cost_pct"], 58.33, places=2)

        # 2. Alert prime cost (> 60%)
        alert = calculate_prime_cost(cogs=3000, labor_cost=2000, gross_sales=6000)
        self.assertEqual(alert["status"], "ALERT")
        self.assertEqual(alert["prime_cost"], 5000.0)
        self.assertAlmostEqual(alert["prime_cost_pct"], 83.33, places=2)

    def test_menu_matrix_kasavana_smith(self):
        sample_items = [
            {"id": 1, "name": "Truffle Pasta", "price": 28.0, "cost": 6.0, "volume": 150},
            {"id": 2, "name": "Steak Burger", "price": 16.0, "cost": 8.0, "volume": 200},
            {"id": 3, "name": "Chilean Sea Bass", "price": 42.0, "cost": 12.0, "volume": 40},
            {"id": 4, "name": "Side Salad", "price": 10.0, "cost": 5.0, "volume": 30}
        ]
        result = calculate_menu_matrix(sample_items)
        self.assertIn("quadrants", result)
        self.assertIn("summary", result)
        self.assertEqual(result["summary"]["stars"], 1)
        self.assertEqual(result["summary"]["plowhorses"], 1)
        self.assertEqual(result["summary"]["puzzles"], 1)
        self.assertEqual(result["summary"]["dogs"], 1)

    def test_endpoints_unauthorized_without_token(self):
        # 1. POST /api/v1/daily-financials without header -> 401
        res1 = self.client.post("/api/v1/daily-financials", json={"gross_sales": 5000, "cogs": 1500, "labor_cost": 1200})
        self.assertEqual(res1.status_code, 401)
        self.assertEqual(res1.get_json()["code"], "UNAUTHORIZED")

        # 2. GET /api/v1/menu-matrix without header -> 401
        res2 = self.client.get("/api/v1/menu-matrix")
        self.assertEqual(res2.status_code, 401)
        self.assertEqual(res2.get_json()["code"], "UNAUTHORIZED")

    def test_endpoints_unauthorized_with_invalid_token(self):
        res = self.client.get("/api/v1/menu-matrix", headers={"Authorization": "Bearer malformed.invalid.token"})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json()["code"], "UNAUTHORIZED")

    @patch("backend.services.supabase_client.supabase.auth.get_user")
    @patch("backend.services.supabase_client.supabase.table")
    def test_authenticated_requests_succeed(self, mock_table, mock_get_user):
        # Mock Supabase Auth
        mock_user = MagicMock()
        mock_user.id = "usr_tenant_test"
        mock_auth_res = MagicMock()
        mock_auth_res.user = mock_user
        mock_get_user.return_value = mock_auth_res

        # Mock Supabase Table Queries
        mock_query = MagicMock()
        mock_table.return_value = mock_query
        mock_query.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.single.return_value = mock_query
        mock_query.insert.return_value = mock_query

        # Mock table dispatch
        current_table = {"name": ""}

        def fake_table(name):
            current_table["name"] = name
            return mock_query

        mock_table.side_effect = fake_table

        def fake_execute():
            res = MagicMock()
            if current_table["name"] == "profiles":
                res.data = {"restaurant_id": "rest_uuid_777", "role": "owner"}
            elif current_table["name"] == "menu_items":
                res.data = [
                    {"id": "item_1", "name": "Artisan Pizza", "category": "Mains", "price": 20.0, "cost": 4.0},
                    {"id": "item_2", "name": "Craft Beer", "category": "Beverages", "price": 8.0, "cost": 3.0}
                ]
            elif current_table["name"] == "item_sales_logs":
                res.data = [
                    {"item_id": "item_1", "quantity": 180},
                    {"item_id": "item_2", "quantity": 250}
                ]
            else:
                res.data = [{"id": 1, "status": "persisted"}]
            return res

        mock_query.execute.side_effect = fake_execute

        headers = {"Authorization": "Bearer mock_valid_jwt_token"}

        # 1. Test POST /api/v1/daily-financials
        post_res = self.client.post(
            "/api/v1/daily-financials",
            headers=headers,
            json={"gross_sales": 8000.0, "cogs": 2400.0, "labor_cost": 2000.0}
        )
        self.assertEqual(post_res.status_code, 201)
        post_data = post_res.get_json()
        self.assertTrue(post_data["success"])
        self.assertEqual(post_data["metrics"]["status"], "HEALTHY")
        self.assertEqual(post_data["metrics"]["prime_cost"], 4400.0)
        self.assertEqual(post_data["metrics"]["prime_cost_pct"], 55.0)

        # 2. Test GET /api/v1/menu-matrix
        get_res = self.client.get("/api/v1/menu-matrix", headers=headers)
        self.assertEqual(get_res.status_code, 200)
        get_data = get_res.get_json()
        self.assertTrue(get_data["success"])
        self.assertEqual(get_data["restaurant_id"], "rest_uuid_777")
        self.assertIn("quadrants", get_data["data"])

if __name__ == "__main__":
    unittest.main()
