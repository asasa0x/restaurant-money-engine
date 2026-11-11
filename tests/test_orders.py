import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from backend.app import create_app
from backend.routes import orders as orders_module

REST_A = "11111111-1111-4111-8111-111111111111"
REST_B = "22222222-2222-4222-8222-222222222222"


class FakeQuery:
    """Tiny in-memory stand-in for the supabase-py query builder."""

    def __init__(self, db, table):
        self.db, self.table = db, table
        self.op, self.payload = "select", None
        self.filters, self._order, self._limit = [], None, None

    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, val):
        self.filters.append(lambda r, c=col, v=val: r.get(c) == v)
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r, c=col, v=list(vals): r.get(c) in v)
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        failure = self.db.failures.get((self.table, self.op))
        if failure:
            raise failure
        rows = self.db.tables.setdefault(self.table, [])
        if self.op == "insert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            created = []
            for item in items:
                row = dict(item)
                row.setdefault("id", str(uuid.uuid4()))
                row.setdefault("created_at", "2026-01-01T00:00:00+00:00")
                rows.append(row)
                created.append(dict(row))
            return SimpleNamespace(data=created)
        matched = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in matched:
                r.update(self.payload)
            return SimpleNamespace(data=[dict(r) for r in matched])
        if self.op == "delete":
            self.db.tables[self.table] = [r for r in rows if r not in matched]
            return SimpleNamespace(data=[dict(r) for r in matched])
        if self._order:
            col, desc = self._order
            matched = sorted(matched, key=lambda r: str(r.get(col, "")), reverse=desc)
        if self._limit:
            matched = matched[: self._limit]
        return SimpleNamespace(data=[dict(r) for r in matched])


class FakeSupabase:
    def __init__(self):
        self.tables, self.failures = {}, {}

    def table(self, name):
        return FakeQuery(self, name)


def make_item(restaurant_id, name, price, cost=40, active=True, category="Pizza"):
    return {
        "id": str(uuid.uuid4()), "restaurant_id": restaurant_id, "name": name, "category": category,
        "selling_price": price, "price": price, "cost_price": cost, "cost": cost, "is_active": active,
    }


class OrderingTestBase(unittest.TestCase):
    def setUp(self):
        orders_module._recent_orders.clear()
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

        self.db = FakeSupabase()
        self.db.tables["restaurants"] = [
            {"id": REST_A, "name": "Pizza Club Sargodha", "currency": "PKR"},
            {"id": REST_B, "name": "Other Cafe", "currency": "USD"},
        ]
        self.pizza = make_item(REST_A, "Pizza Tikka :: Chicken, Onion, Olives", 1400)
        self.burger = make_item(REST_A, "Zinger Burger", 320, category="Burger")
        self.hidden = make_item(REST_A, "Archived Dish", 500, active=False)
        self.foreign = make_item(REST_B, "Other Cafe Latte", 450, category="Drinks")
        self.db.tables["menu_items"] = [self.pizza, self.burger, self.hidden, self.foreign]

        patcher = patch("backend.routes.orders.supabase", self.db)
        patcher.start()
        self.addCleanup(patcher.stop)

    def order_body(self, **overrides):
        body = {
            "customer_name": "Ali",
            "table_number": "5",
            "items": [{"menu_item_id": self.pizza["id"], "quantity": 2},
                      {"menu_item_id": self.burger["id"], "quantity": 1}],
        }
        body.update(overrides)
        return body

    def place(self, restaurant_id=REST_A, body=None):
        return self.client.post(f"/api/v1/public/restaurants/{restaurant_id}/orders",
                                json=body if body is not None else self.order_body())

    def owner_headers(self, restaurant_id):
        auth_sb = MagicMock()
        auth_sb.auth.get_user.return_value = MagicMock(user=MagicMock(id=f"user-{restaurant_id[:4]}"))
        auth_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"restaurant_id": restaurant_id, "role": "owner"}])
        )
        patcher = patch("backend.middleware.auth.supabase", auth_sb)
        patcher.start()
        self.addCleanup(patcher.stop)
        return {"Authorization": "Bearer valid-jwt"}


class TestPublicMenu(OrderingTestBase):
    def test_menu_shows_only_active_items_of_that_restaurant_without_cost_data(self):
        res = self.client.get(f"/api/v1/public/restaurants/{REST_A}/menu")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["restaurant"]["name"], "Pizza Club Sargodha")
        self.assertEqual(body["restaurant"]["currency"], "PKR")
        names = {i["name"] for i in body["items"]}
        self.assertEqual(names, {"Pizza Tikka", "Zinger Burger"})
        pizza = next(i for i in body["items"] if i["name"] == "Pizza Tikka")
        self.assertEqual(pizza["description"], "Chicken, Onion, Olives")
        self.assertEqual(pizza["price"], 1400.0)
        for item in body["items"]:
            self.assertEqual(set(item), {"id", "name", "description", "category", "price"})
        self.assertNotIn("cost", res.get_data(as_text=True).lower())

    def test_unknown_or_malformed_restaurant_is_404(self):
        self.assertEqual(self.client.get("/api/v1/public/restaurants/not-a-uuid/menu").status_code, 404)
        missing = "33333333-3333-4333-8333-333333333333"
        self.assertEqual(self.client.get(f"/api/v1/public/restaurants/{missing}/menu").status_code, 404)

    def test_menu_database_failure_is_5xx(self):
        self.db.failures[("menu_items", "select")] = RuntimeError("secret detail")
        res = self.client.get(f"/api/v1/public/restaurants/{REST_A}/menu")
        self.assertEqual(res.status_code, 500)
        self.assertNotIn("secret detail", res.get_data(as_text=True))


class TestPlaceOrder(OrderingTestBase):
    def test_order_is_priced_from_database_and_stored_for_the_right_restaurant(self):
        body = self.order_body()
        body["items"][0]["unit_price"] = 1          # client-supplied price must be ignored
        body["total"] = 1
        res = self.place(body=body)
        self.assertEqual(res.status_code, 201)
        order = res.get_json()["order"]
        self.assertEqual(order["total"], 1400 * 2 + 320)
        self.assertEqual(order["status"], "pending")
        self.assertEqual(order["currency"], "PKR")
        self.assertEqual(len(order["code"]), 8)

        saved = self.db.tables["orders"][0]
        self.assertEqual(saved["restaurant_id"], REST_A)
        self.assertEqual(saved["total"], 3120.0)
        lines = self.db.tables["order_items"]
        self.assertEqual({l["restaurant_id"] for l in lines}, {REST_A})
        self.assertEqual({l["order_id"] for l in lines}, {saved["id"]})
        self.assertEqual(sorted(l["unit_price"] for l in lines), [320.0, 1400.0])

    def test_duplicate_lines_are_merged(self):
        body = self.order_body(items=[{"menu_item_id": self.burger["id"], "quantity": 1},
                                      {"menu_item_id": self.burger["id"], "quantity": 2}])
        res = self.place(body=body)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["order"]["total"], 960.0)
        self.assertEqual(len(self.db.tables["order_items"]), 1)

    def test_item_from_another_restaurant_is_rejected(self):
        body = self.order_body(items=[{"menu_item_id": self.foreign["id"], "quantity": 1}])
        res = self.place(body=body)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(self.db.tables.get("orders", []), [])

    def test_inactive_item_is_rejected(self):
        body = self.order_body(items=[{"menu_item_id": self.hidden["id"], "quantity": 1}])
        self.assertEqual(self.place(body=body).status_code, 409)
        self.assertEqual(self.db.tables.get("orders", []), [])

    def test_validation_rejects_bad_input(self):
        pid = self.pizza["id"]
        cases = [
            self.order_body(items=[]),
            self.order_body(items=[{"menu_item_id": pid, "quantity": 0}]),
            self.order_body(items=[{"menu_item_id": pid, "quantity": 51}]),
            self.order_body(items=[{"menu_item_id": pid, "quantity": "2"}]),
            self.order_body(items=[{"menu_item_id": pid, "quantity": True}]),
            self.order_body(items=[{"menu_item_id": pid, "quantity": 1.5}]),
            self.order_body(items=[{"menu_item_id": "nope", "quantity": 1}]),
            self.order_body(customer_name=""),
            self.order_body(customer_name="x" * 101),
            self.order_body(table_number=None, customer_phone=None),
        ]
        for body in cases:
            res = self.place(body=body)
            self.assertEqual(res.status_code, 400, body)
        self.assertEqual(self.db.tables.get("orders", []), [])
        self.assertEqual(self.place(restaurant_id="bad", body=self.order_body()).status_code, 404)

    def test_takeaway_order_with_phone_and_no_table(self):
        res = self.place(body=self.order_body(table_number=None, customer_phone="0300-1234567"))
        self.assertEqual(res.status_code, 201)

    def test_order_insert_failure_returns_5xx_and_nothing_saved(self):
        self.db.failures[("orders", "insert")] = RuntimeError("boom-secret")
        res = self.place()
        self.assertEqual(res.status_code, 500)
        self.assertNotIn("boom-secret", res.get_data(as_text=True))
        self.assertFalse(res.get_json()["success"])

    def test_unreachable_database_returns_503(self):
        self.db.failures[("orders", "insert")] = httpx.ConnectError("down")
        self.assertEqual(self.place().status_code, 503)

    def test_line_insert_failure_rolls_back_the_order_header(self):
        self.db.failures[("order_items", "insert")] = RuntimeError("lines failed")
        res = self.place()
        self.assertEqual(res.status_code, 500)
        self.assertEqual(self.db.tables["orders"], [])

    def test_rate_limit_blocks_spam(self):
        for _ in range(orders_module.ORDER_RATE_LIMIT):
            self.assertEqual(self.place().status_code, 201)
        self.assertEqual(self.place().status_code, 429)


class TestTrackOrder(OrderingTestBase):
    def test_tracking_exposes_status_but_no_customer_details(self):
        order_id = self.place().get_json()["order"]["id"]
        res = self.client.get(f"/api/v1/public/orders/{order_id}")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()["order"]
        self.assertEqual(body["status"], "pending")
        self.assertEqual(len(body["items"]), 2)
        text = res.get_data(as_text=True)
        self.assertNotIn("Ali", text)
        self.assertNotIn("customer_phone", text)

    def test_unknown_order_is_404(self):
        self.assertEqual(self.client.get(f"/api/v1/public/orders/{uuid.uuid4()}").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/public/orders/bad").status_code, 404)


class TestOwnerOrders(OrderingTestBase):
    def seed_orders(self):
        self.place()
        self.db.tables["orders"].append({
            "id": str(uuid.uuid4()), "restaurant_id": REST_B, "customer_name": "Stranger",
            "status": "pending", "total": 450, "subtotal": 450, "created_at": "2026-01-02T00:00:00+00:00"})
        return self.db.tables["orders"][0]["id"], self.db.tables["orders"][1]["id"]

    def test_requires_authentication(self):
        self.assertEqual(self.client.get("/api/v1/orders").status_code, 401)
        self.assertEqual(self.client.put(f"/api/v1/orders/{uuid.uuid4()}/status", json={"status": "ready"}).status_code, 401)

    def test_owner_sees_only_own_orders_with_items(self):
        own_id, _ = self.seed_orders()
        res = self.client.get("/api/v1/orders", headers=self.owner_headers(REST_A))
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertEqual([o["id"] for o in data], [own_id])
        self.assertEqual(len(data[0]["items"]), 2)
        self.assertNotIn("Stranger", res.get_data(as_text=True))

    def test_status_filter_and_validation(self):
        self.seed_orders()
        headers = self.owner_headers(REST_A)
        self.assertEqual(self.client.get("/api/v1/orders?status=ready", headers=headers).get_json()["count"], 0)
        self.assertEqual(self.client.get("/api/v1/orders?status=pending", headers=headers).get_json()["count"], 1)
        self.assertEqual(self.client.get("/api/v1/orders?status=bogus", headers=headers).status_code, 400)

    def test_owner_can_update_own_order_status(self):
        own_id, _ = self.seed_orders()
        res = self.client.put(f"/api/v1/orders/{own_id}/status", json={"status": "preparing"},
                              headers=self.owner_headers(REST_A))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.db.tables["orders"][0]["status"], "preparing")

    def test_owner_cannot_update_another_restaurants_order(self):
        _, foreign_id = self.seed_orders()
        res = self.client.put(f"/api/v1/orders/{foreign_id}/status", json={"status": "cancelled"},
                              headers=self.owner_headers(REST_A))
        self.assertEqual(res.status_code, 404)
        foreign = next(o for o in self.db.tables["orders"] if o["id"] == foreign_id)
        self.assertEqual(foreign["status"], "pending")

    def test_invalid_status_rejected(self):
        own_id, _ = self.seed_orders()
        res = self.client.put(f"/api/v1/orders/{own_id}/status", json={"status": "teleported"},
                              headers=self.owner_headers(REST_A))
        self.assertEqual(res.status_code, 400)

    def test_database_failure_listing_orders_is_5xx(self):
        self.db.failures[("orders", "select")] = RuntimeError("db down")
        res = self.client.get("/api/v1/orders", headers=self.owner_headers(REST_A))
        self.assertEqual(res.status_code, 500)


class TestOrderingMigration(unittest.TestCase):
    def test_migration_defines_tables_rls_and_no_anonymous_insert(self):
        from pathlib import Path
        base = Path(__file__).resolve().parent.parent / "database"
        mig = (base / "migrations" / "004_customer_orders.sql").read_text(encoding="utf-8")
        schema = (base / "schema.sql").read_text(encoding="utf-8")
        for text in (mig, schema):
            self.assertIn("CREATE TABLE IF NOT EXISTS public.orders", text)
            self.assertIn("CREATE TABLE IF NOT EXISTS public.order_items", text)
            self.assertIn("ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY", text)
            self.assertIn("ALTER TABLE public.order_items ENABLE ROW LEVEL SECURITY", text)
            self.assertIn("restaurant_id = public.current_restaurant_id()", text)
        self.assertNotRegex(mig, r"FOR INSERT")


class TestCustomerPageStatic(unittest.TestCase):
    def test_customer_page_is_wired_and_never_sends_prices(self):
        from pathlib import Path
        frontend = Path(__file__).resolve().parent.parent / "frontend"
        html = (frontend / "order.html").read_text(encoding="utf-8")
        js = (frontend / "js" / "customer-order.js").read_text(encoding="utf-8")
        for element_id in ("co-menu", "co-cart-bar", "co-cart-modal", "co-checkout-form", "co-success-modal"):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("customer-order.js", html)
        # client sends only ids + quantities; the server prices the order
        self.assertIn("menu_item_id, quantity", js)
        self.assertNotIn("unit_price:", js)
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("Pizza Club Super Supreme", js)

    def test_owner_dashboard_has_orders_and_qr_tab(self):
        from pathlib import Path
        frontend = Path(__file__).resolve().parent.parent / "frontend"
        html = (frontend / "index.html").read_text(encoding="utf-8")
        for element_id in ("tab-orders", "btn-generate-qr", "qr-canvas", "orders-list"):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('data-tab="tab-orders"', html)


if __name__ == "__main__":
    unittest.main()
