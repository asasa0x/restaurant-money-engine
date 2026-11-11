import io
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from backend.app import create_app
from backend.services.menu_scanner import parse_menu_text

BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURE_PATH = BASE_DIR / "tests" / "fixtures" / "pizza_club_sargodha_menu.txt"


class TestMenuScanAndBulkManagement(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.ocr_text = FIXTURE_PATH.read_text(encoding="utf-8")

    def _mock_auth(self, mock_auth_sb, restaurant_id="rest-pizza-club-001", user_id="user-pc-001"):
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_res = MagicMock()
        mock_res.user = mock_user
        mock_auth_sb.auth.get_user.return_value = mock_res
        mock_auth_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"restaurant_id": restaurant_id, "role": "owner"}]
        )

    def test_parse_pizza_club_sargodha_menu_extracts_all_50_items(self):
        """Verify all 50 items across 9 categories are extracted with prices and descriptions."""
        items = parse_menu_text(self.ocr_text, expand_sizes=False)
        self.assertEqual(len(items), 50)

        by_name = {item["name"]: item for item in items}

        # Verify Deal-1, Deal-3 (including '2 Pratha Roll'), Deal-11, Deal-12
        self.assertIn("Deal-1", by_name)
        self.assertEqual(by_name["Deal-1"]["category"], "Deals")
        self.assertEqual(by_name["Deal-1"]["selling_price"], 2550.0)
        self.assertIn("1 Large Pizza", by_name["Deal-1"]["description"])

        self.assertIn("Deal-3", by_name)
        self.assertEqual(by_name["Deal-3"]["selling_price"], 2850.0)
        self.assertIn("2 Pratha Roll", by_name["Deal-3"]["description"])
        self.assertIn("1 Zinger Burger + 1.5 Ltr. Drink", by_name["Deal-3"]["description"])

        self.assertIn("Deal-11", by_name)
        self.assertEqual(by_name["Deal-11"]["selling_price"], 3350.0)

        # Verify Pizzas and multi-size descriptions
        self.assertIn("Pizza Club Super Supreme", by_name)
        sup = by_name["Pizza Club Super Supreme"]
        self.assertEqual(sup["category"], "Pizza")
        self.assertEqual(sup["selling_price"], 650.0)
        self.assertIn("Pepperoni", sup["description"])
        self.assertIn("Small: 650 | Medium: 1400 | Large: 1800 | Family: 2500", sup["description"])

        self.assertIn("Pickle Punjabi Pizza", by_name)
        self.assertEqual(by_name["Pickle Punjabi Pizza"]["category"], "Pizza (New Taste)")
        self.assertIn("Achar, Chicken Boti", by_name["Pickle Punjabi Pizza"]["description"])

        # Verify Fast Food categories (Burger, Shawarma, Paratha Roll, Hot Wings, Fries, Salad)
        self.assertEqual(by_name["Zinger Burger Crispy"]["category"], "Burger")
        self.assertEqual(by_name["Zinger Burger Crispy"]["selling_price"], 320.0)
        self.assertEqual(by_name["Double Dekker Burger"]["selling_price"], 600.0)

        self.assertEqual(by_name["Chicken Shawarma"]["category"], "Shawarma")
        self.assertEqual(by_name["Chicken Shawarma"]["selling_price"], 220.0)
        self.assertEqual(by_name["Nuggets (10 Pcs.) with French Fries"]["selling_price"], 700.0)

        self.assertEqual(by_name["Pizza Club Special Pratha Roll"]["category"], "Paratha Roll")
        self.assertEqual(by_name["Pizza Club Special Pratha Roll"]["selling_price"], 250.0)

        self.assertEqual(by_name["Drumettes Wings (10Pc)"]["category"], "Hot Wings")
        self.assertEqual(by_name["Drumettes Wings (10Pc)"]["selling_price"], 750.0)

        self.assertEqual(by_name["French Fries (Large)"]["category"], "Fries")
        self.assertEqual(by_name["French Fries (Large)"]["selling_price"], 450.0)

        self.assertEqual(by_name["Salad (Large)"]["category"], "Salad")
        self.assertEqual(by_name["Salad (Large)"]["selling_price"], 600.0)

    @patch("backend.middleware.auth.supabase")
    def test_scan_endpoint_multipart_upload_and_json_ocr(self, mock_auth_sb):
        """Verify POST /api/v1/menu/scan works with multipart screenshot upload and JSON payload."""
        self._mock_auth(mock_auth_sb)

        data = {
            "image": (io.BytesIO(b"\xff\xd8\xff\xe0fake-jpeg-bytes"), "pizza_club_menu.jpg"),
            "ocr_text": self.ocr_text,
        }
        res = self.client.post(
            "/api/v1/menu/scan",
            data=data,
            content_type="multipart/form-data",
            headers={"Authorization": "Bearer valid-jwt"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["restaurant_id"], "rest-pizza-club-001")
        self.assertEqual(body["count"], 50)
        self.assertEqual(len(body["items"]), 50)

    @patch("backend.routes.menu.supabase")
    @patch("backend.middleware.auth.supabase")
    def test_bulk_save_and_menu_crud_persistence_with_descriptions(self, mock_auth_sb, mock_menu_sb):
        """Verify POST /api/v1/menu/bulk stamps tenant restaurant_id and unpacks descriptions on GET/PUT/DELETE."""
        self._mock_auth(mock_auth_sb, restaurant_id="rest-pizza-club-001")

        extracted = parse_menu_text(self.ocr_text)
        captured_insert = []

        def fake_insert(records):
            for idx, r in enumerate(records, 1):
                row = dict(r)
                row["id"] = f"item-uuid-{idx}"
                captured_insert.append(row)
            mock_exec = MagicMock()
            mock_exec.execute.return_value = MagicMock(data=[dict(r) for r in captured_insert])
            return mock_exec

        mock_menu_sb.table.return_value.insert.side_effect = fake_insert

        res_bulk = self.client.post(
            "/api/v1/menu/bulk",
            json={"items": extracted},
            headers={"Authorization": "Bearer valid-jwt"},
        )
        self.assertEqual(res_bulk.status_code, 201)
        bulk_body = res_bulk.get_json()
        self.assertEqual(bulk_body["inserted_count"], 50)
        self.assertEqual(bulk_body["restaurant_id"], "rest-pizza-club-001")

        # Every DB row must be stamped with caller's restaurant_id
        self.assertTrue(all(r["restaurant_id"] == "rest-pizza-club-001" for r in captured_insert))

        # Verify unpacked name & description in response
        first_saved = bulk_body["data"][0]
        self.assertEqual(first_saved["name"], "Deal-1")
        self.assertIn("1 Large Pizza", first_saved["description"])

        # Verify GET /api/v1/menu/ unpacks descriptions cleanly
        mock_menu_sb.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value = MagicMock(
            data=[dict(r) for r in captured_insert]
        )
        res_get = self.client.get("/api/v1/menu/", headers={"Authorization": "Bearer valid-jwt"})
        self.assertEqual(res_get.status_code, 200)
        get_body = res_get.get_json()
        self.assertEqual(get_body["count"], 50)
        self.assertEqual(get_body["data"][0]["name"], "Deal-1")
        self.assertIn("1 Large Pizza", get_body["data"][0]["description"])

        # Verify PUT /api/v1/menu/<id> updates name, price, category, and description
        mock_menu_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "item-uuid-1",
                "restaurant_id": "rest-pizza-club-001",
                "name": "Deal-1 Special :: Updated Combo Description",
                "category": "Deals",
                "selling_price": 2650.0,
                "cost_price": 850.0,
                "is_active": True,
            }]
        )
        res_put = self.client.put(
            "/api/v1/menu/item-uuid-1",
            json={
                "name": "Deal-1 Special",
                "category": "Deals",
                "selling_price": 2650.0,
                "cost_price": 850.0,
                "description": "Updated Combo Description",
            },
            headers={"Authorization": "Bearer valid-jwt"},
        )
        self.assertEqual(res_put.status_code, 200)
        put_data = res_put.get_json()["data"]
        self.assertEqual(put_data["name"], "Deal-1 Special")
        self.assertEqual(put_data["selling_price"], 2650.0)
        self.assertEqual(put_data["description"], "Updated Combo Description")

        # Verify DELETE /api/v1/menu/<id>?permanent=true
        mock_menu_sb.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "item-uuid-50"}]
        )
        res_del = self.client.delete(
            "/api/v1/menu/item-uuid-50?permanent=true",
            headers={"Authorization": "Bearer valid-jwt"},
        )
        self.assertEqual(res_del.status_code, 200)
        self.assertIn("deleted", res_del.get_json()["message"])

    def test_pizza_club_menu_is_not_hardcoded_in_app_code(self):
        """Ensure Pizza Club Sargodha menu items are not hardcoded in backend or frontend code."""
        app_files = list((BASE_DIR / "backend").rglob("*.py")) + list((BASE_DIR / "frontend").rglob("*.js"))
        for f in app_files:
            text = f.read_text(encoding="utf-8")
            self.assertNotIn("Pizza Club Super Supreme", text, f"Hardcoded menu item found in {f}")
            self.assertNotIn("Pickle Punjabi Pizza", text, f"Hardcoded menu item found in {f}")
            self.assertNotIn("KATCHERY ROAD", text, f"Hardcoded restaurant address found in {f}")


if __name__ == "__main__":
    unittest.main()

