from typing import List, Dict, Any

def calculate_prime_cost(
    cogs: float,
    labor_cost: float,
    gross_sales: float,
    target_prime_cost_pct: float = 60.0
) -> Dict[str, Any]:
    """
    Calculate restaurant Prime Cost and Prime Cost Percentage.
    - prime_cost = cogs + labor_cost
    - prime_cost_pct = (prime_cost / gross_sales) * 100
    - status = HEALTHY if prime_cost_pct <= target_prime_cost_pct else ALERT
    """
    cogs_val = float(cogs or 0.0)
    labor_val = float(labor_cost or 0.0)
    sales_val = float(gross_sales or 0.0)

    prime_cost = round(cogs_val + labor_val, 2)
    
    if sales_val > 0:
        prime_cost_pct = round((prime_cost / sales_val) * 100, 2)
    else:
        prime_cost_pct = 0.0

    status = "HEALTHY" if prime_cost_pct <= target_prime_cost_pct else "ALERT"

    return {
        "gross_sales": sales_val,
        "cogs": cogs_val,
        "labor_cost": labor_val,
        "prime_cost": prime_cost,
        "prime_cost_pct": prime_cost_pct,
        "target_prime_cost_pct": target_prime_cost_pct,
        "status": status
    }

def calculate_menu_matrix(items_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Kasavana-Smith Menu Engineering Matrix classification:
    - ACM = Average Contribution Margin
    - Popularity Threshold = 70% of Average Volume (or (1/N) * 0.70 * Total Volume)
    Quadrants:
    - Stars: High Margin, High Volume
    - Plowhorses: Low Margin, High Volume
    - Puzzles: High Margin, Low Volume
    - Dogs: Low Margin, Low Volume
    """
    if not items_data:
        return {
            "items": [],
            "quadrants": {"stars": [], "plowhorses": [], "puzzles": [], "dogs": []},
            "benchmarks": {
                "average_contribution_margin": 0.0,
                "popularity_threshold": 0.0,
                "average_volume": 0.0,
                "total_volume": 0
            },
            "summary": {"stars": 0, "plowhorses": 0, "puzzles": 0, "dogs": 0}
        }

    parsed_items = []
    total_volume = 0
    total_gross_profit = 0.0

    for item in items_data:
        price = float(item.get("price") or item.get("sale_price") or 0.0)
        cost = float(item.get("cost") or item.get("cost_price") or 0.0)
        volume = int(item.get("volume") or item.get("quantity") or item.get("total_sold") or 0)
        
        cm = round(price - cost, 2)
        food_cost_pct = round((cost / price * 100), 1) if price > 0 else 0.0
        total_profit = round(cm * volume, 2)

        total_volume += volume
        total_gross_profit += total_profit

        parsed_items.append({
            "id": item.get("id"),
            "name": item.get("name", "Unnamed Item"),
            "category": item.get("category", "General"),
            "price": price,
            "cost": cost,
            "volume": volume,
            "contribution_margin": cm,
            "food_cost_pct": food_cost_pct,
            "total_profit": total_profit
        })

    n = len(parsed_items)
    
    # Average Contribution Margin (ACM)
    if total_volume > 0:
        acm = total_gross_profit / total_volume
    else:
        acm = sum(i["contribution_margin"] for i in parsed_items) / n

    # Popularity Threshold (Kasavana & Smith 70% hurdle rate)
    avg_volume = total_volume / n
    popularity_threshold = avg_volume * 0.70

    stars, plowhorses, puzzles, dogs = [], [], [], []

    for item in parsed_items:
        is_high_margin = item["contribution_margin"] >= acm
        is_high_volume = item["volume"] >= popularity_threshold

        if is_high_margin and is_high_volume:
            quadrant = "Stars"
            action = "High profitability & high demand. Protect recipe consistency and highlight in prime menu eye-spots."
            stars.append(item)
        elif (not is_high_margin) and is_high_volume:
            quadrant = "Plowhorses"
            action = "High volume with lower margin. Test gradual price increases or portion control to reduce ingredient cost."
            plowhorses.append(item)
        elif is_high_margin and (not is_high_volume):
            quadrant = "Puzzles"
            action = "High profitability but under-ordered. Feature in chef specials, redesign menu placement, and train staff to upsell."
            puzzles.append(item)
        else:
            quadrant = "Dogs"
            action = "Low volume and low profit. Re-engineer ingredients to cut cost or consider retiring from menu."
            dogs.append(item)

        item["quadrant"] = quadrant
        item["action_recommendation"] = action

    return {
        "items": parsed_items,
        "quadrants": {
            "stars": stars,
            "plowhorses": plowhorses,
            "puzzles": puzzles,
            "dogs": dogs
        },
        "benchmarks": {
            "average_contribution_margin": round(acm, 2),
            "popularity_threshold": round(popularity_threshold, 2),
            "average_volume": round(avg_volume, 2),
            "total_volume": total_volume
        },
        "summary": {
            "stars": len(stars),
            "plowhorses": len(plowhorses),
            "puzzles": len(puzzles),
            "dogs": len(dogs)
        }
    }

def calculate_recipe_cost(ingredients: List[Dict[str, Any]]) -> float:
    """
    Sums (quantity * unit_cost) for an ingredient breakdown to calculate portion food cost.
    """
    if not ingredients:
        return 0.0

    total_cost = 0.0
    for ing in ingredients:
        qty = float(ing.get("quantity") or 0.0)
        cost = float(ing.get("unit_cost") or 0.0)
        total_cost += qty * cost

    return round(total_cost, 2)

def simulate_profit_impact(
    current_financials: Dict[str, Any],
    ingredient_inflation_pct: float = 0.0,
    price_change_pct: float = 0.0,
    labor_change_pct: float = 0.0
) -> Dict[str, Any]:
    """
    Projects revised Gross Sales, COGS, Labor Cost, and Net Prime Cost Margin under what-if scenarios:
    - ingredient_inflation_pct: % change in ingredient wholesale costs
    - price_change_pct: % change in menu selling prices
    - labor_change_pct: % change in labor wages/hours
    """
    base_sales = float(current_financials.get("gross_sales") or current_financials.get("revenue") or 0.0)
    base_cogs = float(current_financials.get("cogs") or current_financials.get("food_cost") or 0.0)
    base_labor = float(current_financials.get("labor_cost") or 0.0)

    base_prime = round(base_cogs + base_labor, 2)
    base_prime_pct = round((base_prime / base_sales) * 100, 2) if base_sales > 0 else 0.0
    base_margin = round(base_sales - base_prime, 2)
    base_margin_pct = round((base_margin / base_sales) * 100, 2) if base_sales > 0 else 0.0

    # Multipliers
    p_mult = 1.0 + (float(price_change_pct or 0.0) / 100.0)
    c_mult = 1.0 + (float(ingredient_inflation_pct or 0.0) / 100.0)
    l_mult = 1.0 + (float(labor_change_pct or 0.0) / 100.0)

    proj_sales = round(base_sales * p_mult, 2)
    proj_cogs = round(base_cogs * c_mult, 2)
    proj_labor = round(base_labor * l_mult, 2)
    proj_prime = round(proj_cogs + proj_labor, 2)
    proj_prime_pct = round((proj_prime / proj_sales) * 100, 2) if proj_sales > 0 else 0.0
    proj_margin = round(proj_sales - proj_prime, 2)
    proj_margin_pct = round((proj_margin / proj_sales) * 100, 2) if proj_sales > 0 else 0.0

    margin_delta = round(proj_margin - base_margin, 2)
    margin_delta_pct = round((margin_delta / abs(base_margin)) * 100, 2) if base_margin != 0 else 0.0

    return {
        "parameters": {
            "ingredient_inflation_pct": float(ingredient_inflation_pct or 0.0),
            "price_change_pct": float(price_change_pct or 0.0),
            "labor_change_pct": float(labor_change_pct or 0.0)
        },
        "baseline": {
            "gross_sales": base_sales,
            "cogs": base_cogs,
            "labor_cost": base_labor,
            "prime_cost": base_prime,
            "prime_cost_pct": base_prime_pct,
            "prime_margin": base_margin,
            "prime_margin_pct": base_margin_pct
        },
        "projected": {
            "gross_sales": proj_sales,
            "cogs": proj_cogs,
            "labor_cost": proj_labor,
            "prime_cost": proj_prime,
            "prime_cost_pct": proj_prime_pct,
            "prime_margin": proj_margin,
            "prime_margin_pct": proj_margin_pct
        },
        "impact": {
            "gross_sales_delta": round(proj_sales - base_sales, 2),
            "cogs_delta": round(proj_cogs - base_cogs, 2),
            "labor_cost_delta": round(proj_labor - base_labor, 2),
            "prime_cost_delta": round(proj_prime - base_prime, 2),
            "margin_delta": margin_delta,
            "margin_delta_pct": margin_delta_pct,
            "prime_pct_delta": round(proj_prime_pct - base_prime_pct, 2),
            "is_gain": margin_delta >= 0
        }
    }
