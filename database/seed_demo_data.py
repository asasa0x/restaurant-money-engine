#!/usr/bin/env python3
"""
Seed & Demo Data Script for Restaurant Money Engine
Populates Supabase with 1 demo restaurant, 8 menu items across all 4 Kasavana-Smith quadrants,
sample ingredient recipes, and 7 days of daily financials.

Usage:
    python database/seed_demo_data.py
    python database/seed_demo_data.py --clean
"""

import sys
import argparse
from datetime import date, timedelta
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.services.supabase_client import supabase

DEMO_RESTAURANT_ID = "rest_demo_777"
DEMO_RESTAURANT_NAME = "L'Osteria Downtown (Primary)"

DEMO_MENU_ITEMS = [
    # ⭐ Stars: High Margin, High Popularity
    {"id": "item_demo_01", "name": "Truffle Tagliatelle", "category": "Mains", "selling_price": 28.00, "cost_price": 6.20, "is_active": True},
    {"id": "item_demo_02", "name": "Old Fashioned Cocktail", "category": "Beverages", "selling_price": 16.00, "cost_price": 2.80, "is_active": True},

    # 🐎 Plowhorses: Low Margin, High Popularity
    {"id": "item_demo_03", "name": "Prime Ribeye Steak 12oz", "category": "Mains", "selling_price": 38.00, "cost_price": 17.50, "is_active": True},
    {"id": "item_demo_04", "name": "Crispy Calamari", "category": "Appetizers", "selling_price": 15.00, "cost_price": 7.20, "is_active": True},

    # 🧩 Puzzles: High Margin, Low Popularity
    {"id": "item_demo_05", "name": "Pan-Seared Chilean Sea Bass", "category": "Mains", "selling_price": 42.00, "cost_price": 11.00, "is_active": True},
    {"id": "item_demo_06", "name": "Burrata Caprese", "category": "Appetizers", "selling_price": 18.00, "cost_price": 3.90, "is_active": True},

    # 🐕 Dogs: Low Margin, Low Popularity
    {"id": "item_demo_07", "name": "House Caesar Salad", "category": "Appetizers", "selling_price": 13.00, "cost_price": 6.50, "is_active": True},
    {"id": "item_demo_08", "name": "Vegetarian Grain Bowl", "category": "Mains", "selling_price": 19.00, "cost_price": 8.20, "is_active": True}
]

DEMO_RECIPES = [
    # Truffle Tagliatelle ingredients
    {"menu_item_id": "item_demo_01", "ingredient_name": "Fresh Egg Tagliatelle", "quantity": 0.180, "unit": "kg", "unit_cost": 6.00},
    {"menu_item_id": "item_demo_01", "ingredient_name": "Black Truffle Butter", "quantity": 0.030, "unit": "kg", "unit_cost": 45.00},
    {"menu_item_id": "item_demo_01", "ingredient_name": "Parmigiano-Reggiano", "quantity": 0.040, "unit": "kg", "unit_cost": 22.00},
    {"menu_item_id": "item_demo_01", "ingredient_name": "Heavy Cream", "quantity": 0.060, "unit": "l", "unit_cost": 5.00},

    # Prime Ribeye ingredients
    {"menu_item_id": "item_demo_03", "ingredient_name": "USDA Prime Ribeye", "quantity": 0.350, "unit": "kg", "unit_cost": 42.00},
    {"menu_item_id": "item_demo_03", "ingredient_name": "Herb Compound Butter", "quantity": 0.030, "unit": "kg", "unit_cost": 18.00},
    {"menu_item_id": "item_demo_03", "ingredient_name": "Thyme & Garlic Garnish", "quantity": 1.000, "unit": "portion", "unit_cost": 0.50}
]

def generate_financials():
    """Generate 7 trailing days of realistic restaurant financial records."""
    today = date.today()
    days_data = [
        # (days_ago, gross_sales, cogs, labor_cost)
        (6, 6800.00, 1970.00, 2040.00), # Monday
        (5, 7200.00, 2088.00, 2160.00), # Tuesday
        (4, 7950.00, 2305.00, 2385.00), # Wednesday
        (3, 8900.00, 2580.00, 2670.00), # Thursday
        (2, 11400.00, 3306.00, 3420.00),# Friday Rush
        (1, 12800.00, 3712.00, 3840.00),# Saturday Peak
        (0, 9450.00, 2740.00, 2835.00)  # Sunday
    ]
    records = []
    for ago, sales, cogs, labor in days_data:
        entry_date = (today - timedelta(days=ago)).isoformat()
        prime = round(cogs + labor, 2)
        pct = round((prime / sales) * 100, 1)
        records.append({
            "restaurant_id": DEMO_RESTAURANT_ID,
            "date": entry_date,
            "gross_sales": sales,
            "cogs": cogs,
            "labor_cost": labor,
            "prime_cost": prime,
            "prime_cost_pct": pct,
            "status": "HEALTHY" if pct <= 60.0 else "ALERT"
        })
    return records

def clean_demo_data():
    """Purge existing demo data from Supabase."""
    print(f"🧹 Purging demo data for restaurant ID: {DEMO_RESTAURANT_ID}...")
    try:
        # Delete recipes
        for item in DEMO_MENU_ITEMS:
            supabase.table("recipes").delete().eq("menu_item_id", item["id"]).execute()
        # Delete menu items
        supabase.table("menu_items").delete().eq("restaurant_id", DEMO_RESTAURANT_ID).execute()
        # Delete financials
        supabase.table("daily_financials").delete().eq("restaurant_id", DEMO_RESTAURANT_ID).execute()
        # Delete restaurant record
        supabase.table("restaurants").delete().eq("id", DEMO_RESTAURANT_ID).execute()
        print("✓ Demo data purged successfully!")
    except Exception as exc:
        print(f"Notice during purge: {exc}")

def seed_demo_data():
    """Insert complete demo dataset into Supabase."""
    print(f"🌱 Seeding demo data for restaurant: {DEMO_RESTAURANT_NAME} ({DEMO_RESTAURANT_ID})...")

    # 1. Seed Restaurant
    try:
        supabase.table("restaurants").upsert({
            "id": DEMO_RESTAURANT_ID,
            "name": DEMO_RESTAURANT_NAME,
            "currency": "USD"
        }).execute()
        print("  ✓ Restaurant entity seeded.")
    except Exception as e:
        print(f"  - Restaurant table notice: {e}")

    # 2. Seed Menu Items
    try:
        items_payload = []
        for item in DEMO_MENU_ITEMS:
            items_payload.append({
                "id": item["id"],
                "restaurant_id": DEMO_RESTAURANT_ID,
                "name": item["name"],
                "category": item["category"],
                "selling_price": item["selling_price"],
                "price": item["selling_price"],
                "cost_price": item["cost_price"],
                "cost": item["cost_price"],
                "is_active": item["is_active"]
            })
        supabase.table("menu_items").upsert(items_payload).execute()
        print(f"  ✓ {len(items_payload)} Menu items seeded across 4 quadrants.")
    except Exception as e:
        print(f"  - Menu items table notice: {e}")

    # 3. Seed Recipes
    try:
        supabase.table("recipes").upsert(DEMO_RECIPES).execute()
        print(f"  ✓ {len(DEMO_RECIPES)} Recipe ingredients seeded.")
    except Exception as e:
        print(f"  - Recipes table notice: {e}")

    # 4. Seed Daily Financials
    try:
        financials = generate_financials()
        supabase.table("daily_financials").upsert(financials).execute()
        print(f"  ✓ {len(financials)} Daily financial records seeded.")
    except Exception as e:
        print(f"  - Daily financials table notice: {e}")

    print("🎉 Demo seeding process complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo dataset into Supabase for Restaurant Money Engine.")
    parser.add_argument("--clean", action="store_true", help="Purge demo data from Supabase")
    args = parser.parse_args()

    if args.clean:
        clean_demo_data()
    else:
        seed_demo_data()

