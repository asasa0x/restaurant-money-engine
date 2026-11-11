import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from backend.app import create_app

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


class TestAuthAndLiveFrontendIntegration(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("backend.routes.auth.restore_service_role_auth")
    @patch("backend.routes.auth.supabase")
    def test_signup_creates_user_restaurant_profile_and_returns_token(self, mock_sb, _mock_restore):
        mock_user = MagicMock()
        mock_user.id = "user-uuid-101"
        mock_user_res = MagicMock()
        mock_user_res.user = mock_user
        mock_sb.auth.admin.create_user.return_value = mock_user_res

        mock_session = MagicMock()
        mock_session.access_token = "jwt-live-token-101"
        mock_sign_in = MagicMock()
        mock_sign_in.session = mock_session
        mock_sb.auth.sign_in_with_password.return_value = mock_sign_in

        def table_side_effect(name):
            tbl = MagicMock()
            if name == "restaurants":
                tbl.insert.return_value.execute.return_value = MagicMock(
                    data=[{"id": "rest-uuid-101", "name": "Bistro Roma", "currency": "USD"}]
                )
            elif name == "profiles":
                tbl.insert.return_value.execute.return_value = MagicMock(
                    data=[{"id": "user-uuid-101", "restaurant_id": "rest-uuid-101", "role": "owner"}]
                )
            return tbl

        mock_sb.table.side_effect = table_side_effect

        res = self.client.post("/api/v1/auth/signup", json={
            "email": "Owner@BistroRoma.com",
            "password": "securePassword123",
            "restaurant_name": "Bistro Roma"
        })
        self.assertEqual(res.status_code, 201)
        body = res.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["access_token"], "jwt-live-token-101")
        self.assertEqual(body["user"]["email"], "owner@bistroroma.com")
        self.assertEqual(body["user"]["role"], "owner")
        self.assertEqual(body["restaurant"]["id"], "rest-uuid-101")
        self.assertEqual(body["restaurant"]["name"], "Bistro Roma")

    def test_signup_validation_rejects_invalid_inputs(self):
        res1 = self.client.post("/api/v1/auth/signup", json={
            "email": "not-an-email",
            "password": "securePassword123",
            "restaurant_name": "Bistro"
        })
        self.assertEqual(res1.status_code, 400)

        res2 = self.client.post("/api/v1/auth/signup", json={
            "email": "valid@bistro.com",
            "password": "123",
            "restaurant_name": "Bistro"
        })
        self.assertEqual(res2.status_code, 400)

        res3 = self.client.post("/api/v1/auth/signup", json={
            "email": "valid@bistro.com",
            "password": "securePassword123",
            "restaurant_name": "   "
        })
        self.assertEqual(res3.status_code, 400)

    @patch("backend.routes.auth.restore_service_role_auth")
    @patch("backend.routes.auth.supabase")
    def test_login_returns_session_and_restaurant(self, mock_sb, _mock_restore):
        mock_user = MagicMock()
        mock_user.id = "user-uuid-202"
        mock_user.email = "chef@bistro.com"
        mock_session = MagicMock()
        mock_session.access_token = "jwt-token-202"
        mock_sign_in = MagicMock()
        mock_sign_in.user = mock_user
        mock_sign_in.session = mock_session
        mock_sb.auth.sign_in_with_password.return_value = mock_sign_in

        def table_side_effect(name):
            tbl = MagicMock()
            if name == "profiles":
                tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"restaurant_id": "rest-uuid-202", "role": "owner"}]
                )
            elif name == "restaurants":
                tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"id": "rest-uuid-202", "name": "Chef Kitchen", "currency": "USD"}]
                )
            return tbl

        mock_sb.table.side_effect = table_side_effect

        res = self.client.post("/api/v1/auth/login", json={
            "email": "chef@bistro.com",
            "password": "password123"
        })
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["access_token"], "jwt-token-202")
        self.assertEqual(body["restaurant"]["name"], "Chef Kitchen")

    @patch("backend.routes.auth.restore_service_role_auth")
    @patch("backend.routes.auth.supabase")
    def test_login_fails_closed_when_profile_missing(self, mock_sb, _mock_restore):
        mock_user = MagicMock()
        mock_user.id = "user-no-profile"
        mock_session = MagicMock()
        mock_session.access_token = "jwt-token-orphan"
        mock_sign_in = MagicMock()
        mock_sign_in.user = mock_user
        mock_sign_in.session = mock_session
        mock_sb.auth.sign_in_with_password.return_value = mock_sign_in

        tbl = MagicMock()
        tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        mock_sb.table.return_value = tbl

        res = self.client.post("/api/v1/auth/login", json={
            "email": "orphan@bistro.com",
            "password": "password123"
        })
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json()["code"], "PROFILE_NOT_FOUND")

    @patch("backend.routes.engine.supabase")
    @patch("backend.middleware.auth.supabase")
    def test_get_daily_financials_returns_latest_and_empty_states(self, mock_auth_sb, mock_engine_sb):
        mock_user = MagicMock()
        mock_user.id = "u-1"
        mock_auth_res = MagicMock()
        mock_auth_res.user = mock_user
        mock_auth_sb.auth.get_user.return_value = mock_auth_res
        mock_auth_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"restaurant_id": "rest-1", "role": "owner"}]
        )

        # Case 1: Empty daily_financials
        mock_engine_sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        res_empty = self.client.get(
            "/api/v1/daily-financials",
            headers={"Authorization": "Bearer valid-jwt"}
        )
        self.assertEqual(res_empty.status_code, 200)
        empty_body = res_empty.get_json()
        self.assertFalse(empty_body["has_data"])
        self.assertEqual(empty_body["data"]["status"], "NO_DATA")

        # Case 2: Populated daily_financials
        mock_engine_sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{
                "date": "2026-11-09",
                "gross_sales": 10000.0,
                "cogs": 2800.0,
                "labor_cost": 2700.0,
                "prime_cost": 5500.0,
                "prime_cost_pct": 55.0,
                "status": "HEALTHY"
            }]
        )
        res_pop = self.client.get(
            "/api/v1/daily-financials",
            headers={"Authorization": "Bearer valid-jwt"}
        )
        self.assertEqual(res_pop.status_code, 200)
        pop_body = res_pop.get_json()
        self.assertTrue(pop_body["has_data"])
        self.assertEqual(pop_body["data"]["gross_sales"], 10000.0)
        self.assertEqual(pop_body["data"]["prime_cost_pct"], 55.0)
        self.assertEqual(pop_body["data"]["status"], "HEALTHY")

    def test_frontend_has_no_demo_store_or_silent_fallback(self):
        js_files = list((FRONTEND_DIR / "js").glob("*.js"))
        self.assertGreaterEqual(len(js_files), 5)

        for js_file in js_files:
            content = js_file.read_text(encoding="utf-8")
            self.assertNotIn("DEMO_STORE", content, f"{js_file.name} still references DEMO_STORE")
            self.assertNotIn("__isFallback", content, f"{js_file.name} still uses __isFallback")

        html_content = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("rest_demo_777", html_content)
        self.assertIn("auth-email-input", html_content)
        self.assertIn("auth-password-input", html_content)
        self.assertIn("auth-restaurant-name", html_content)


if __name__ == "__main__":
    unittest.main()

