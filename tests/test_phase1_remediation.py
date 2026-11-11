"""
Phase 1 remediation tests.

These tests use an in-memory fake of the Supabase client containing two synthetic
restaurants (rest-1 / rest-2). They prove APPLICATION-LAYER behavior: fail-closed auth,
tenant-scoped queries, recipe ownership checks, DB error handling, prime cost and config
validation. They do NOT prove database-level RLS or behavior against a real Supabase project.
"""
import copy
import subprocess
import sys
import unittest
import uuid
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from dotenv import dotenv_values

from backend.app import create_app
from backend.config import Config, validate_production_config
from backend.middleware.tenant import TenantContextError, current_restaurant_id
from backend.services.money_engine import calculate_prime_cost
from backend.services.supabase_client import supabase

ROOT = Path(__file__).resolve().parent.parent

R1, R2 = "rest-1", "rest-2"
Query = namedtuple("Query", "table op filters payload")

TOKENS = {
    "token-alice": "u_alice",   # restaurant rest-1
    "token-bob": "u_bob",       # restaurant rest-2
    "token-carol": "u_carol",   # authenticated, NO profile row
    "token-dave": "u_dave",     # profile row with restaurant_id = None
}


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.op, self.payload, self.filters, self.limit_n = "select", None, [], None

    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def insert(self, payload, **_k):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload, **_k):
        self.op, self.payload = "update", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self.filters.append(("in", col, list(vals)))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def _match(self, row):
        for kind, col, val in self.filters:
            if kind == "eq" and row.get(col) != val:
                return False
            if kind == "in" and row.get(col) not in val:
                return False
        return True

    def execute(self):
        self.db.log.append(Query(self.table, self.op, tuple(self.filters), copy.deepcopy(self.payload)))
        failure = self.db.pop_failure(self.table, self.op)
        if failure is not None:
            raise failure
        if self.op in ("update", "delete") and not self.filters:
            raise AssertionError(f"Unscoped {self.op} on {self.table} (no filters)")
        rows = self.db.tables.setdefault(self.table, [])
        if self.op == "select":
            out = [copy.deepcopy(r) for r in rows if self._match(r)]
            return SimpleNamespace(data=out[: self.limit_n] if self.limit_n else out)
        if self.op == "insert":
            recs = self.payload if isinstance(self.payload, list) else [self.payload]
            created = []
            for rec in recs:
                rec = dict(rec)
                rec.setdefault("id", str(uuid.uuid4()))
                rows.append(rec)
                created.append(copy.deepcopy(rec))
            return SimpleNamespace(data=created)
        if self.op == "update":
            hit = [r for r in rows if self._match(r)]
            for r in hit:
                r.update(self.payload)
            return SimpleNamespace(data=copy.deepcopy(hit))
        hit = [r for r in rows if self._match(r)]
        self.db.tables[self.table] = [r for r in rows if not self._match(r)]
        return SimpleNamespace(data=copy.deepcopy(hit))


class FakeDB:
    def __init__(self):
        self.log = []
        self.failures = {}
        self.tables = {
            "profiles": [
                {"id": "u_alice", "restaurant_id": R1, "role": "owner"},
                {"id": "u_bob", "restaurant_id": R2, "role": "owner"},
                {"id": "u_dave", "restaurant_id": None, "role": "member"},
            ],
            "menu_items": [
                self._item("m1", R1, "Pasta", 20.0, 5.0),
                self._item("m2", R1, "Steak", 40.0, 15.0),
                self._item("m3", R2, "Burger", 15.0, 6.0),
            ],
            "recipes": [
                {"id": "rc1", "menu_item_id": "m1", "ingredient_name": "Flour", "quantity": 1.0, "unit": "kg", "unit_cost": 2.0},
                {"id": "rc2", "menu_item_id": "m1", "ingredient_name": "Egg", "quantity": 2.0, "unit": "pc", "unit_cost": 0.5},
                {"id": "rc3", "menu_item_id": "m3", "ingredient_name": "Beef", "quantity": 0.2, "unit": "kg", "unit_cost": 15.0},
            ],
            "item_sales_logs": [
                {"id": "s1", "restaurant_id": R1, "item_id": "m1", "quantity": 100},
                {"id": "s2", "restaurant_id": R1, "item_id": "m2", "quantity": 50},
                {"id": "s3", "restaurant_id": R2, "item_id": "m3", "quantity": 70},
            ],
            "daily_financials": [
                {"id": "d1", "restaurant_id": R1, "date": "2026-01-01", "gross_sales": 1000.0, "cogs": 300.0, "labor_cost": 300.0},
                {"id": "d2", "restaurant_id": R1, "date": "2026-01-02", "gross_sales": 3000.0, "cogs": 900.0, "labor_cost": 900.0},
                {"id": "d3", "restaurant_id": R2, "date": "2026-01-01", "gross_sales": 5000.0, "cogs": 1000.0, "labor_cost": 1000.0},
            ],
        }

    @staticmethod
    def _item(item_id, rid, name, price, cost):
        return {"id": item_id, "restaurant_id": rid, "name": name, "category": "Mains",
                "selling_price": price, "price": price, "cost_price": cost, "cost": cost, "is_active": True}

    def table(self, name):
        return FakeQuery(self, name)

    def fail(self, table, op, exc, times=None):
        self.failures[(table, op)] = [exc, times]

    def pop_failure(self, table, op):
        entry = self.failures.get((table, op))
        if not entry:
            return None
        exc, times = entry
        if times is not None:
            entry[1] -= 1
            if entry[1] <= 0:
                del self.failures[(table, op)]
        return exc

    def data_queries(self):
        return [q for q in self.log if q.table != "profiles"]

    def rows(self, table, **match):
        return [r for r in self.tables[table] if all(r.get(k) == v for k, v in match.items())]


def fake_get_user(token):
    if token not in TOKENS:
        raise Exception("invalid JWT")
    return SimpleNamespace(user=SimpleNamespace(id=TOKENS[token]))


class BaseApiTest(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.app = create_app()
        self.client = self.app.test_client()
        for p in (
            patch.object(supabase, "table", side_effect=self.db.table),
            patch.object(supabase.auth, "get_user", side_effect=fake_get_user),
        ):
            p.start()
            self.addCleanup(p.stop)

    def call(self, method, url, token="token-alice", json=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return getattr(self.client, method)(url, headers=headers, json=json)


VALID_DAILY = {"gross_sales": 1000, "cogs": 300, "labor_cost": 250}
ALL_ENDPOINTS = [
    ("get", "/api/v1/menu/", None),
    ("post", "/api/v1/menu/", {"name": "X", "selling_price": 1}),
    ("put", "/api/v1/menu/m1", {"name": "Y"}),
    ("delete", "/api/v1/menu/m1", None),
    ("get", "/api/v1/menu/m1/recipe", None),
    ("post", "/api/v1/menu/m1/recipe", {"ingredients": []}),
    ("get", "/api/v1/menu-matrix", None),
    ("post", "/api/v1/daily-financials", VALID_DAILY),
    ("post", "/api/v1/simulation/run", {"price_change_pct": 5}),
]


class TestMissingProfileFailsClosed(BaseApiTest):
    def test_user_without_profile_gets_403_everywhere(self):
        before = copy.deepcopy(self.db.tables)
        for method, url, body in ALL_ENDPOINTS:
            with self.subTest(endpoint=f"{method.upper()} {url}"):
                res = self.call(method, url, token="token-carol", json=body)
                self.assertEqual(res.status_code, 403)
                self.assertFalse(res.get_json()["success"])
                self.assertEqual(res.get_json()["code"], "PROFILE_NOT_FOUND")
        self.assertEqual(self.db.data_queries(), [], "no data table may be queried without a restaurant")
        self.assertEqual(self.db.tables, before)

    def test_profile_without_restaurant_id_gets_403_everywhere(self):
        before = copy.deepcopy(self.db.tables)
        for method, url, body in ALL_ENDPOINTS:
            with self.subTest(endpoint=f"{method.upper()} {url}"):
                res = self.call(method, url, token="token-dave", json=body)
                self.assertEqual(res.status_code, 403)
                self.assertEqual(res.get_json()["code"], "RESTAURANT_NOT_ASSIGNED")
        self.assertEqual(self.db.data_queries(), [])
        self.assertEqual(self.db.tables, before)

    def test_profile_lookup_database_failure_is_5xx_and_returns_no_data(self):
        self.db.fail("profiles", "select", Exception("boom-secret-detail"))
        res = self.call("get", "/api/v1/menu/")
        self.assertIn(res.status_code, (500, 503))
        self.assertFalse(res.get_json()["success"])
        self.assertNotIn("boom-secret-detail", res.get_data(as_text=True))
        self.assertEqual(self.db.data_queries(), [])

    def test_tenant_helper_raises_and_handler_returns_403_without_context(self):
        with self.app.test_request_context("/"):
            with self.assertRaises(TenantContextError):
                current_restaurant_id()

        app = create_app()

        @app.route("/_probe")
        def probe():
            current_restaurant_id()
            return "should-not-reach"

        res = app.test_client().get("/_probe")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json()["code"], "FORBIDDEN_NO_RESTAURANT")

    def test_invalid_token_is_401_without_leaking_provider_error(self):
        res = self.call("get", "/api/v1/menu/", token="token-unknown")
        self.assertEqual(res.status_code, 401)
        self.assertNotIn("invalid JWT", res.get_data(as_text=True))

    def test_auth_service_unreachable_is_503_not_401(self):
        with patch.object(supabase.auth, "get_user", side_effect=httpx.ConnectError("refused")):
            res = self.call("get", "/api/v1/menu/")
        self.assertEqual(res.status_code, 503)


class TestCrossRestaurantIsolation(BaseApiTest):
    def test_menu_list_only_returns_own_restaurant(self):
        alice = self.call("get", "/api/v1/menu/", token="token-alice").get_json()
        bob = self.call("get", "/api/v1/menu/", token="token-bob").get_json()
        self.assertEqual({i["id"] for i in alice["data"]}, {"m1", "m2"})
        self.assertEqual({i["id"] for i in bob["data"]}, {"m3"})
        self.assertTrue(all(i["restaurant_id"] == R1 for i in alice["data"]))

    def test_other_restaurant_cannot_update_or_archive_item(self):
        before = copy.deepcopy(self.db.rows("menu_items", id="m1"))
        res = self.call("put", "/api/v1/menu/m1", token="token-bob", json={"selling_price": 1, "name": "HACKED"})
        self.assertEqual(res.status_code, 404)
        res = self.call("delete", "/api/v1/menu/m1", token="token-bob")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(self.db.rows("menu_items", id="m1"), before)

    def test_create_ignores_restaurant_id_from_payload(self):
        res = self.call("post", "/api/v1/menu/", token="token-alice",
                        json={"name": "Spoof", "selling_price": 9, "restaurant_id": R2})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self.db.rows("menu_items", name="Spoof")[0]["restaurant_id"], R1)

    def test_matrix_only_uses_own_items_and_sales(self):
        alice = self.call("get", "/api/v1/menu-matrix", token="token-alice").get_json()
        bob = self.call("get", "/api/v1/menu-matrix", token="token-bob").get_json()
        self.assertEqual({i["id"] for i in alice["data"]["items"]}, {"m1", "m2"})
        self.assertEqual(alice["data"]["benchmarks"]["total_volume"], 150)
        self.assertEqual({i["id"] for i in bob["data"]["items"]}, {"m3"})
        self.assertEqual(bob["data"]["benchmarks"]["total_volume"], 70)

    def test_daily_financials_stamped_with_callers_restaurant(self):
        res = self.call("post", "/api/v1/daily-financials", token="token-bob",
                        json={**VALID_DAILY, "restaurant_id": R1})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["saved_record"]["restaurant_id"], R2)
        self.assertEqual(len(self.db.rows("daily_financials", restaurant_id=R1)), 2)

    def test_simulation_baseline_comes_only_from_own_restaurant(self):
        alice = self.call("post", "/api/v1/simulation/run", token="token-alice", json={}).get_json()
        bob = self.call("post", "/api/v1/simulation/run", token="token-bob", json={}).get_json()
        self.assertEqual(alice["simulation"]["baseline"]["gross_sales"], 4000.0)
        self.assertEqual(bob["simulation"]["baseline"]["gross_sales"], 5000.0)

    def test_every_data_query_is_scoped_to_callers_restaurant(self):
        flows = [
            ("get", "/api/v1/menu/", None),
            ("post", "/api/v1/menu/", {"name": "Scoped", "selling_price": 5}),
            ("put", "/api/v1/menu/m1", {"selling_price": 21}),
            ("delete", "/api/v1/menu/m2", None),
            ("get", "/api/v1/menu/m1/recipe", None),
            ("post", "/api/v1/menu/m1/recipe",
             {"ingredients": [{"ingredient_name": "Salt", "quantity": 1, "unit": "kg", "unit_cost": 1}]}),
            ("get", "/api/v1/menu-matrix", None),
            ("post", "/api/v1/daily-financials", VALID_DAILY),
            ("post", "/api/v1/simulation/run", {"price_change_pct": 3}),
        ]
        for method, url, body in flows:
            res = self.call(method, url, token="token-alice", json=body)
            self.assertIn(res.status_code, (200, 201), f"{method} {url} -> {res.get_data(as_text=True)}")

        tenant_tables = {"menu_items", "item_sales_logs", "daily_financials"}
        checked = 0
        for q in self.db.log:
            if q.table in tenant_tables:
                checked += 1
                if q.op == "insert":
                    self.assertEqual(q.payload["restaurant_id"], R1, q)
                else:
                    self.assertIn(("eq", "restaurant_id", R1), q.filters, f"unscoped query: {q}")
        self.assertGreater(checked, 8)


class TestRecipeOwnership(BaseApiTest):
    def recipes_queries(self):
        return [q for q in self.db.log if q.table == "recipes"]

    def test_foreign_item_recipe_read_is_404_and_never_touches_recipes(self):
        res = self.call("get", "/api/v1/menu/m1/recipe", token="token-bob")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(self.recipes_queries(), [])
        self.assertNotIn("Flour", res.get_data(as_text=True))

    def test_foreign_item_recipe_write_is_404_and_leaves_recipes_untouched(self):
        before = copy.deepcopy(self.db.tables["recipes"])
        res = self.call("post", "/api/v1/menu/m1/recipe", token="token-bob",
                        json={"ingredients": [{"ingredient_name": "Evil", "quantity": 1, "unit": "kg", "unit_cost": 1}]})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(self.recipes_queries(), [])
        self.assertEqual(self.db.tables["recipes"], before)
        self.assertEqual(self.db.rows("menu_items", id="m1")[0]["cost_price"], 5.0)

    def test_nonexistent_item_is_404_without_recipe_queries(self):
        for method, body in (("get", None), ("post", {"ingredients": []})):
            res = self.call(method, "/api/v1/menu/does-not-exist/recipe", json=body)
            self.assertEqual(res.status_code, 404)
        self.assertEqual(self.recipes_queries(), [])

    def test_owner_flow_verifies_ownership_before_any_recipe_query(self):
        self.assertEqual(self.call("get", "/api/v1/menu/m1/recipe").status_code, 200)
        res = self.call("post", "/api/v1/menu/m1/recipe", json={"ingredients": [
            {"ingredient_name": "Tomato", "quantity": 0.5, "unit": "kg", "unit_cost": 4.0},
            {"ingredient_name": "Basil", "quantity": 1, "unit": "portion", "unit_cost": 0.25}]})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["calculated_cost_price"], 2.25)

        for i, q in enumerate(self.db.log):
            if q.table == "recipes":
                earlier = [e for e in self.db.log[:i] if e.table == "menu_items" and e.op == "select"
                           and ("eq", "id", "m1") in e.filters and ("eq", "restaurant_id", R1) in e.filters]
                self.assertTrue(earlier, f"recipe query without prior ownership check: {q}")
        self.assertEqual({r["ingredient_name"] for r in self.db.rows("recipes", menu_item_id="m1")}, {"Tomato", "Basil"})
        self.assertEqual(self.db.rows("menu_items", id="m1")[0]["cost_price"], 2.25)

    def test_other_restaurants_recipes_are_never_modified_by_owner_calls(self):
        self.call("post", "/api/v1/menu/m1/recipe", json={"ingredients": []})
        self.assertEqual(len(self.db.rows("recipes", menu_item_id="m3")), 1)

    def test_invalid_ingredients_rejected_with_400_and_nothing_changes(self):
        before = copy.deepcopy(self.db.tables["recipes"])
        bad_payloads = [
            [{"ingredient_name": "", "quantity": 1, "unit": "kg", "unit_cost": 1}],
            [{"ingredient_name": "A", "quantity": -1, "unit": "kg", "unit_cost": 1}],
            [{"ingredient_name": "A", "quantity": 1, "unit": "kg", "unit_cost": "NaN"}],
            ["not-an-object"],
        ]
        for ingredients in bad_payloads:
            res = self.call("post", "/api/v1/menu/m1/recipe", json={"ingredients": ingredients})
            self.assertEqual(res.status_code, 400, ingredients)
        self.assertEqual(self.db.tables["recipes"], before)


class TestDatabaseFailuresAreNotHiddenAsSuccess(BaseApiTest):
    SECRET = "boom-secret-detail"

    def assert_db_failure(self, res):
        self.assertIn(res.status_code, (500, 503), res.get_data(as_text=True))
        body = res.get_json()
        self.assertFalse(body["success"])
        self.assertIn(body["code"], ("DATABASE_ERROR", "DATABASE_UNAVAILABLE"))
        self.assertNotIn(self.SECRET, res.get_data(as_text=True))

    def test_each_endpoint_returns_5xx_when_its_query_fails(self):
        cases = [
            ("get", "/api/v1/menu/", None, "menu_items", "select"),
            ("post", "/api/v1/menu/", {"name": "N", "selling_price": 5}, "menu_items", "insert"),
            ("put", "/api/v1/menu/m1", {"name": "Z"}, "menu_items", "update"),
            ("delete", "/api/v1/menu/m1", None, "menu_items", "update"),
            ("get", "/api/v1/menu/m1/recipe", None, "recipes", "select"),
            ("get", "/api/v1/menu/m1/recipe", None, "menu_items", "select"),
            ("post", "/api/v1/menu/m1/recipe", {"ingredients": []}, "menu_items", "select"),
            ("get", "/api/v1/menu-matrix", None, "menu_items", "select"),
            ("get", "/api/v1/menu-matrix", None, "item_sales_logs", "select"),
            ("post", "/api/v1/daily-financials", VALID_DAILY, "daily_financials", "insert"),
            ("post", "/api/v1/simulation/run", {}, "daily_financials", "select"),
        ]
        for method, url, body, table, op in cases:
            for exc in (Exception(self.SECRET), httpx.ConnectError(self.SECRET)):
                with self.subTest(endpoint=f"{method.upper()} {url}", failing=f"{table}.{op}", exc=type(exc).__name__):
                    self.db = FakeDB()
                    self.db.fail(table, op, exc)
                    with patch.object(supabase, "table", side_effect=self.db.table):
                        res = self.call(method, url, json=body)
                    self.assert_db_failure(res)
                    if isinstance(exc, httpx.ConnectError):
                        self.assertEqual(res.status_code, 503)

    def test_failed_create_does_not_return_fake_item_and_stores_nothing(self):
        self.db.fail("menu_items", "insert", Exception(self.SECRET))
        res = self.call("post", "/api/v1/menu/", json={"name": "Ghost", "selling_price": 5})
        self.assert_db_failure(res)
        self.assertEqual(self.db.rows("menu_items", name="Ghost"), [])

    def test_failed_daily_insert_stores_nothing(self):
        self.db.fail("daily_financials", "insert", Exception(self.SECRET))
        self.assert_db_failure(self.call("post", "/api/v1/daily-financials", json=VALID_DAILY))
        self.assertEqual(len(self.db.rows("daily_financials", restaurant_id=R1)), 2)

    def test_failed_recipe_insert_keeps_previous_recipe(self):
        self.db.fail("recipes", "insert", Exception(self.SECRET))
        res = self.call("post", "/api/v1/menu/m1/recipe", json={"ingredients": [
            {"ingredient_name": "New", "quantity": 1, "unit": "kg", "unit_cost": 1}]})
        self.assert_db_failure(res)
        self.assertEqual({r["id"] for r in self.db.rows("recipes", menu_item_id="m1")}, {"rc1", "rc2"})
        self.assertEqual(self.db.rows("menu_items", id="m1")[0]["cost_price"], 5.0)

    def test_failed_old_recipe_removal_rolls_back_new_rows(self):
        self.db.fail("recipes", "delete", Exception(self.SECRET), times=1)
        res = self.call("post", "/api/v1/menu/m1/recipe", json={"ingredients": [
            {"ingredient_name": "New", "quantity": 1, "unit": "kg", "unit_cost": 1}]})
        self.assert_db_failure(res)
        self.assertEqual({r["id"] for r in self.db.rows("recipes", menu_item_id="m1")}, {"rc1", "rc2"})

    def test_failed_cost_update_after_recipe_change_is_reported(self):
        self.db.fail("menu_items", "update", Exception(self.SECRET))
        res = self.call("post", "/api/v1/menu/m1/recipe", json={"ingredients": [
            {"ingredient_name": "New", "quantity": 1, "unit": "kg", "unit_cost": 1}]})
        self.assert_db_failure(res)


class TestNoInventedSimulationData(BaseApiTest):
    def test_restaurant_without_financials_gets_422_not_made_up_numbers(self):
        self.db.tables["daily_financials"] = []
        res = self.call("post", "/api/v1/simulation/run", json={"price_change_pct": 5})
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.get_json()["code"], "NO_BASELINE_DATA")

    def test_explicit_baseline_is_used_when_provided(self):
        self.db.tables["daily_financials"] = []
        res = self.call("post", "/api/v1/simulation/run", json={
            "price_change_pct": 5, "ingredient_inflation_pct": 4, "labor_change_pct": 2,
            "baseline_financials": {"gross_sales": 100000, "cogs": 30000, "labor_cost": 30000}})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["simulation"]["impact"]["margin_delta"], 3200.0)

    def test_invalid_percentages_are_400(self):
        for body in ({"price_change_pct": "abc"}, {"labor_change_pct": "NaN"}, {"price_change_pct": -500}):
            res = self.call("post", "/api/v1/simulation/run", json=body)
            self.assertEqual(res.status_code, 400, body)


class TestPrimeCostZeroSales(BaseApiTest):
    def test_zero_sales_with_costs_is_alert_never_healthy(self):
        for sales in (0, 0.0, None, -50, float("nan")):
            r = calculate_prime_cost(cogs=100, labor_cost=50, gross_sales=sales)
            self.assertEqual(r["status"], "ALERT", sales)
            self.assertIsNone(r["prime_cost_pct"])
            self.assertEqual(r["prime_cost"], 150.0)

    def test_zero_sales_and_zero_costs_is_no_data_never_healthy(self):
        r = calculate_prime_cost(cogs=0, labor_cost=0, gross_sales=0)
        self.assertEqual(r["status"], "NO_DATA")
        self.assertIsNone(r["prime_cost_pct"])

    def test_normal_calculations_unchanged(self):
        self.assertEqual(calculate_prime_cost(2000, 1500, 6000)["status"], "HEALTHY")
        self.assertEqual(calculate_prime_cost(3000, 2000, 6000)["status"], "ALERT")
        self.assertEqual(calculate_prime_cost(30, 30, 100)["status"], "HEALTHY")  # exactly 60%
        self.assertEqual(calculate_prime_cost(18705, 19350, 64500)["prime_cost_pct"], 59.0)

    def test_api_rejects_zero_negative_and_non_finite_inputs(self):
        before = len(self.db.tables["daily_financials"])
        bad = [
            {"gross_sales": 0, "cogs": 0, "labor_cost": 0},
            {"gross_sales": -5, "cogs": 1, "labor_cost": 1},
            {"gross_sales": 100, "cogs": -1, "labor_cost": 1},
            {"gross_sales": "NaN", "cogs": 1, "labor_cost": 1},
            {"gross_sales": 100, "cogs": "Infinity", "labor_cost": 1},
            {"gross_sales": True, "cogs": 1, "labor_cost": 1},
            {"gross_sales": 100, "cogs": 1, "labor_cost": 1, "target_prime_cost_pct": "x"},
            {"gross_sales": 100, "cogs": 1, "labor_cost": 1, "date": "not-a-date"},
        ]
        for body in bad:
            res = self.call("post", "/api/v1/daily-financials", json=body)
            self.assertEqual(res.status_code, 400, body)
        self.assertEqual(len(self.db.tables["daily_financials"]), before)


class TestSecretKeyConfiguration(unittest.TestCase):
    @staticmethod
    def cfg(env, secret):
        return type("Cfg", (Config,), {"ENV": env, "SECRET_KEY": secret})

    def test_production_without_secret_fails_startup(self):
        for secret in (None, "", "   "):
            with self.assertRaises(RuntimeError):
                create_app(config_class=self.cfg("production", secret))

    def test_production_with_placeholder_or_short_secret_fails(self):
        for secret in ("dev-secret-key-replace-in-production", "your-flask-secret-key-change-me", "short-key", "a" * 31):
            with self.assertRaises(RuntimeError, msg=secret):
                validate_production_config(self.cfg("production", secret))

    def test_production_with_strong_secret_starts(self):
        secret = "x7Qm2" * 8
        app = create_app(config_class=self.cfg("production", secret))
        self.assertEqual(app.config["SECRET_KEY"], secret)

    def test_development_does_not_require_secret_and_has_no_hardcoded_default(self):
        validate_production_config(self.cfg("development", None))
        self.assertTrue(Config.SECRET_KEY)
        self.assertFalse(str(Config.SECRET_KEY).lower().startswith("dev-secret"))

    def test_real_process_refuses_to_boot_in_production_without_secret(self):
        env_file = dotenv_values(ROOT / ".env") if (ROOT / ".env").is_file() else {}
        if "SECRET_KEY" in env_file or "FLASK_ENV" in env_file:
            self.skipTest(".env defines SECRET_KEY/FLASK_ENV and overrides the process environment")
        import os
        env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
        env["FLASK_ENV"] = "production"
        proc = subprocess.run([sys.executable, "-c", "import backend.app"], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=120)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("SECRET_KEY", proc.stderr)


if __name__ == "__main__":
    unittest.main()
