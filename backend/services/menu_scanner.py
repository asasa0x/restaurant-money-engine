"""
Menu Scanner & Intelligent OCR/Vision Extraction Service.

Supports:
1. Vision AI extraction (Gemini Vision / OpenAI Vision) when API keys are configured in environment.
2. General-purpose structured OCR text parsing for multi-column restaurant menus, combo deals,
   size matrices (Small / Medium / Large / Family), and category-grouped item lists.
"""

import base64
import json
import logging
import os
import re
import httpx

logger = logging.getLogger(__name__)

KNOWN_CATEGORY_HEADERS = {
    "DEALS": "Deals",
    "HOT DEALS": "Deals",
    "COMBO DEALS": "Deals",
    "PIZZA": "Pizza",
    "PIZZAS": "Pizza",
    "NEW TASTE FOR PIZZA LOVER": "Pizza (New Taste)",
    "NEW TASTE FOR PIZZA LOVERS": "Pizza (New Taste)",
    "FAST FOOD": "Fast Food",
    "BURGER": "Burger",
    "BURGERS": "Burger",
    "SHAWARMA": "Shawarma",
    "PARATHA ROLL": "Paratha Roll",
    "PRATHA ROLL": "Paratha Roll",
    "ROLLS": "Paratha Roll",
    "HOT WINGS": "Hot Wings",
    "WINGS": "Hot Wings",
    "FRIES": "Fries",
    "SALAD": "Salad",
    "SALADS": "Salad",
    "APPETIZERS": "Appetizers",
    "STARTERS": "Appetizers",
    "MAINS": "Mains",
    "BEVERAGES": "Beverages",
    "DRINKS": "Beverages",
    "DESSERTS": "Desserts",
    "SIDES": "Sides",
}

DEFAULT_COST_RATIO = 0.32  # Default 32% estimated food cost when only selling price is on menu


def _estimate_cost(selling_price: float) -> float:
    return round(float(selling_price) * DEFAULT_COST_RATIO, 2)


def _normalize_extracted_item(raw: dict) -> dict | None:
    """Validate and normalize a single candidate menu item dict."""
    if not isinstance(raw, dict):
        return None

    name = str(raw.get("name") or "").strip()
    if not name:
        return None

    raw_price = raw.get("selling_price") if raw.get("selling_price") is not None else raw.get("price")
    try:
        selling_price = round(float(raw_price), 2)
    except (TypeError, ValueError):
        return None

    if selling_price < 0:
        return None

    raw_cost = raw.get("cost_price") if raw.get("cost_price") is not None else raw.get("cost")
    if raw_cost is not None and raw_cost != "":
        try:
            cost_price = max(0.0, round(float(raw_cost), 2))
        except (TypeError, ValueError):
            cost_price = _estimate_cost(selling_price)
    else:
        cost_price = _estimate_cost(selling_price)

    category = str(raw.get("category") or "General").strip() or "General"
    description = str(raw.get("description") or "").strip()

    return {
        "name": name,
        "category": category,
        "selling_price": selling_price,
        "cost_price": cost_price,
        "description": description,
        "is_active": True,
    }


def parse_menu_text(raw_text: str, expand_sizes: bool = False) -> list[dict]:
    """
    Parse raw OCR or structured menu text into a list of normalized menu item dicts.
    Handles:
    - Deal headers with inline price (e.g. 'Deal-1 2550RS') + multi-line combo descriptions
    - Multi-column size tables (e.g. 'SMALL MEDIUM LARGE FAMILY' -> 'Pizza Name 650 1400 1800 2500')
      with ingredient descriptions on the following line
    - Category headers ('BURGER', 'SHAWARMA', 'PARATHA ROLL', 'HOT WINGS', 'FRIES', 'SALAD')
    - Single-price item lines ('Zinger Burger Crispy 320' or 'Item Name - Rs. 320')
    """
    if not raw_text or not str(raw_text).strip():
        return []

    lines = [line.strip() for line in str(raw_text).splitlines()]
    items: list[dict] = []
    current_category = "General"
    size_headers: list[str] = []

    # Regex patterns
    deal_header_re = re.compile(
        r"^(Deal[-\s]*(?:\d+|[IVX]+))\s*[:\-|]?\s*(?:Rs\.?\s*)?(\d+(?:\.\d{1,2})?)\s*(?:RS|PKR|/-)?$",
        re.IGNORECASE,
    )
    size_header_re = re.compile(
        r"(?:^|\b)(SMALL)\s+(MEDIUM)\s+(LARGE)(?:\s+(FAMILY|XL|JUMBO))?\b",
        re.IGNORECASE,
    )
    multi_price_row_re = re.compile(
        r"^([A-Za-z][A-Za-z0-9\s\.\-&'()/]+?)\s+"
        r"(\d{2,5}(?:\.\d{1,2})?)\s*[\|/]?\s*"
        r"(\d{2,5}(?:\.\d{1,2})?)\s*[\|/]?\s*"
        r"(\d{2,5}(?:\.\d{1,2})?)"
        r"(?:\s*[\|/]?\s*(\d{2,5}(?:\.\d{1,2})?))?$"
    )
    single_price_row_re = re.compile(
        r"^([A-Za-z][A-Za-z0-9\s\.\-&'()/]+?)\s*[:\-–\.…]+\s*(?:Rs\.?\s*|\$)?(\d+(?:\.\d{1,2})?)\s*(?:RS|PKR|/-)?$"
        r"|"
        r"^([A-Za-z][A-Za-z0-9\s\.\-&'()/]+?)\s+(?:Rs\.?\s*|\$)?(\d{2,5}(?:\.\d{1,2})?)\s*(?:RS|PKR|/-)?$",
        re.IGNORECASE,
    )

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line:
            i += 1
            continue

        # Skip non-menu metadata lines (phone numbers, addresses, timings, delivery banner)
        upper_line = line.upper()
        if any(
            skip in upper_line
            for skip in (
                "TIMING:",
                "DELIVERY CHARGES",
                "ROAD,",
                "TEL:",
                "MOB:",
                "TASTE NEVER BEFORE",
                "PRESS",
            )
        ):
            i += 1
            continue

        # 1. Check if line is a multi-size table header (possibly preceded by a section title)
        size_match = size_header_re.search(line)
        if size_match:
            prefix = line[: size_match.start()].strip(" -:|")
            if prefix:
                norm_prefix = prefix.upper()
                current_category = KNOWN_CATEGORY_HEADERS.get(norm_prefix, prefix.title())
            elif current_category == "General":
                current_category = "Pizza"
            size_headers = [s.title() for s in size_match.groups() if s]
            i += 1
            continue

        # 2. Check if line is a known category header (must not contain leading item quantities like '2 Pratha Roll')
        cleaned_header = re.sub(r"[^A-Z0-9\s]", "", upper_line).strip()
        if cleaned_header in KNOWN_CATEGORY_HEADERS:
            current_category = KNOWN_CATEGORY_HEADERS[cleaned_header]
            if current_category not in ("Pizza", "Pizza (New Taste)"):
                size_headers = []
            i += 1
            continue

        # 3. Check for Deal header line (e.g. 'Deal-1 2550RS')
        deal_match = deal_header_re.match(line)
        if deal_match:
            deal_name = re.sub(r"\s+", "-", deal_match.group(1).strip())
            # Normalize Roman numerals like Deal-I -> Deal-1, Deal-II -> Deal-11 if needed
            if deal_name.upper() == "DEAL-I":
                deal_name = "Deal-1"
            elif deal_name.upper() == "DEAL-II":
                deal_name = "Deal-11"
            deal_price = float(deal_match.group(2))

            desc_parts = []
            i += 1
            while i < n and lines[i]:
                next_line = lines[i]
                if (
                    deal_header_re.match(next_line)
                    or size_header_re.search(next_line)
                    or re.sub(r"[^A-Z0-9\s]", "", next_line.upper()).strip() in KNOWN_CATEGORY_HEADERS
                    or multi_price_row_re.match(next_line)
                ):
                    break
                desc_parts.append(next_line)
                i += 1

            items.append({
                "name": deal_name,
                "category": "Deals",
                "selling_price": deal_price,
                "cost_price": _estimate_cost(deal_price),
                "description": ", ".join(desc_parts),
                "is_active": True,
            })
            continue

        # 4. Check for Multi-Price Size Matrix Row (e.g. 'Supreme Pizza 650 1400 1800 2500')
        mp_match = multi_price_row_re.match(line)
        if mp_match:
            raw_dish_name = mp_match.group(1).strip(" -:|")
            # Strip leading 'New ' badge prefix if present while noting it
            dish_name = re.sub(r"^New\s+", "", raw_dish_name, flags=re.IGNORECASE).strip()
            prices = [float(p) for p in mp_match.groups()[1:] if p is not None]
            labels = size_headers if len(size_headers) >= len(prices) else ["Small", "Medium", "Large", "Family"][: len(prices)]

            # Check if the next line(s) are ingredient descriptions (not a header, not a price row)
            desc_parts = []
            i += 1
            while i < n and lines[i]:
                peek = lines[i]
                peek_upper = re.sub(r"[^A-Z0-9\s]", "", peek.upper()).strip()
                if (
                    deal_header_re.match(peek)
                    or size_header_re.search(peek)
                    or peek_upper in KNOWN_CATEGORY_HEADERS
                    or multi_price_row_re.match(peek)
                    or single_price_row_re.match(peek)
                ):
                    break
                desc_parts.append(peek)
                i += 1

            ing_desc = ", ".join(desc_parts)
            cat = current_category if current_category != "General" else "Pizza"

            if expand_sizes:
                for label, p_val in zip(labels, prices):
                    items.append({
                        "name": f"{dish_name} ({label})",
                        "category": cat,
                        "selling_price": p_val,
                        "cost_price": _estimate_cost(p_val),
                        "description": ing_desc,
                        "is_active": True,
                    })
            else:
                size_summary = " | ".join(f"{lbl}: {int(p) if p.is_integer() else p}" for lbl, p in zip(labels, prices))
                full_desc = f"{ing_desc} ({size_summary})" if ing_desc else f"Sizes: {size_summary}"
                # Use Small price (or first column price) as starting base selling_price
                base_price = prices[0]
                items.append({
                    "name": dish_name,
                    "category": cat,
                    "selling_price": base_price,
                    "cost_price": _estimate_cost(base_price),
                    "description": full_desc,
                    "is_active": True,
                })
            continue

        # 5. Check for Single-Price Item Row (e.g. 'Zinger Burger Crispy 320')
        sp_match = single_price_row_re.match(line)
        if sp_match:
            item_name = (sp_match.group(1) or sp_match.group(3) or "").strip(" -:|.")
            price_str = sp_match.group(2) or sp_match.group(4)
            if item_name and price_str:
                price_val = float(price_str)
                items.append({
                    "name": item_name,
                    "category": current_category,
                    "selling_price": price_val,
                    "cost_price": _estimate_cost(price_val),
                    "description": "",
                    "is_active": True,
                })
                i += 1
                continue

        i += 1

    return items


def _extract_via_gemini_vision(image_bytes: bytes, mime_type: str, api_key: str) -> list[dict]:
    """Use Gemini Vision REST API to extract menu items from an uploaded screenshot."""
    b64_data = base64.b64encode(image_bytes).decode("ascii")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    prompt = (
        "Extract every menu item from this restaurant menu image. "
        "Return ONLY a valid JSON object with key 'items', where each element has: "
        "'name' (string), 'category' (string), 'selling_price' (number), "
        "'cost_price' (number, estimate 30% of selling_price if unknown), and 'description' (string, ingredients/combo details or size pricing)."
    )
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": b64_data}},
            ]
        }],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    resp = httpx.post(url, json=payload, timeout=30.0)
    resp.raise_for_status()
    candidates = resp.json().get("candidates") or []
    text = candidates[0]["content"]["parts"][0]["text"]
    parsed = json.loads(text)
    raw_items = parsed.get("items") if isinstance(parsed, dict) else parsed
    return [norm for r in (raw_items or []) if (norm := _normalize_extracted_item(r))]


def scan_menu_payload(
    image_bytes: bytes | None = None,
    mime_type: str = "image/jpeg",
    ocr_text: str | None = None,
    candidate_items: list | None = None,
    expand_sizes: bool = False,
) -> dict:
    """
    Unified menu extraction pipeline:
    1. If structured candidate_items are provided, normalizes and validates them.
    2. If ocr_text is provided, parses it into structured items via parse_menu_text().
    3. If image_bytes is provided and GEMINI_API_KEY / GOOGLE_API_KEY is configured, runs Vision AI.
    """
    extracted: list[dict] = []
    source = "none"

    if isinstance(candidate_items, list) and candidate_items:
        for item in candidate_items:
            norm = _normalize_extracted_item(item)
            if norm:
                extracted.append(norm)
        source = "structured_items"

    if not extracted and ocr_text and str(ocr_text).strip():
        extracted = parse_menu_text(str(ocr_text), expand_sizes=expand_sizes)
        source = "ocr_text_parser"

    if not extracted and image_bytes:
        gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
        if gemini_key:
            try:
                extracted = _extract_via_gemini_vision(image_bytes, mime_type, gemini_key)
                source = "gemini_vision"
            except Exception as exc:
                logger.warning("Gemini Vision extraction failed: %s", type(exc).__name__)

    return {
        "source": source,
        "count": len(extracted),
        "items": extracted,
    }
