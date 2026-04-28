"""
Synthetic B2B Data Generator
Produces realistic product listings mimicking IndiaMART / TradeIndia data.
Used when live sites block scraping, to demonstrate the full EDA pipeline.
"""

import random
import json
import csv
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

# ── Master data pools ──────────────────────────────────────────────────────

CATEGORIES = {
    "Industrial Machinery": {
        "products": [
            "CNC Milling Machine", "Hydraulic Press Machine", "Industrial Conveyor Belt",
            "Lathe Machine", "Injection Moulding Machine", "Centrifugal Pump",
            "Air Compressor", "Industrial Boiler", "Cutting Machine", "Welding Machine",
            "Grinding Machine", "Drilling Machine", "Packaging Machine", "Mixing Machine",
            "Crane Hoist", "Industrial Blower", "Gear Box", "Vibration Screen",
            "Screw Conveyor", "Roller Mill",
        ],
        "price_range": (50000, 5000000),
        "units": ["piece", "set", "unit"],
        "moq": ["1 Unit", "1 Set", "2 Units", "5 Units"],
    },
    "Electronics": {
        "products": [
            "SMPS Power Supply", "LED Driver Board", "Microcontroller Module",
            "Industrial Sensor", "PCB Assembly", "Transformer Core",
            "Capacitor Bank", "Voltage Regulator", "Circuit Breaker",
            "BLDC Motor Controller", "Solar Inverter", "UPS System",
            "Servo Drive", "PLC Controller", "HMI Panel", "Variable Frequency Drive",
            "Temperature Controller", "Current Transducer", "Signal Converter",
            "Embedded System Board",
        ],
        "price_range": (500, 150000),
        "units": ["piece", "unit", "box"],
        "moq": ["10 Pieces", "50 Pieces", "100 Pieces", "1 Box", "5 Units"],
    },
    "Textiles": {
        "products": [
            "Cotton Fabric", "Polyester Yarn", "Silk Saree", "Denim Fabric",
            "Terry Towel", "Knitted Fabric", "Jute Bag", "Linen Cloth",
            "Viscose Rayon", "Nylon Thread", "Woollen Blanket", "Microfiber Fabric",
            "Spandex Lycra", "Georgette Fabric", "Chiffon Material",
            "Cotton Yarn", "Synthetic Fiber", "Blended Fabric", "Canvas Cloth",
            "Embroidered Fabric",
        ],
        "price_range": (50, 5000),
        "units": ["meter", "kg", "piece", "dozen"],
        "moq": ["100 Meters", "500 Meters", "50 Kg", "100 Kg", "1000 Pieces"],
    },
    "Chemical": {
        "products": [
            "Sodium Hydroxide", "Hydrochloric Acid", "Sulphuric Acid",
            "Titanium Dioxide", "Calcium Carbonate", "Sodium Bicarbonate",
            "Acetic Acid", "Nitric Acid", "Phosphoric Acid",
            "Industrial Solvent", "Epoxy Resin", "Polyurethane Foam",
            "Activated Carbon", "Silica Gel", "Ferric Chloride",
            "Potassium Permanganate", "Hydrogen Peroxide", "Ammonia Solution",
            "Zinc Oxide", "Magnesium Sulphate",
        ],
        "price_range": (20, 50000),
        "units": ["kg", "litre", "MT", "drum"],
        "moq": ["25 Kg", "50 Kg", "100 Kg", "500 Kg", "1 MT"],
    },
    "Agriculture": {
        "products": [
            "Tractor Rotavator", "Seed Drill Machine", "Drip Irrigation System",
            "Sprinkler System", "Crop Harvester", "Thresher Machine",
            "Power Tiller", "Agro Spray Pump", "Greenhouse Shade Net",
            "Vermicompost Bin", "Soil Testing Kit", "Mulching Film",
            "Agricultural Sprayer", "Chaff Cutter Machine", "Rice Mill Machine",
            "Water Pump Set", "Farm Plough", "Seed Sorting Machine",
            "Cold Storage Unit", "Solar Water Pump",
        ],
        "price_range": (2000, 800000),
        "units": ["piece", "set", "unit"],
        "moq": ["1 Unit", "1 Set", "2 Sets", "5 Units"],
    },
}

INDIAN_CITIES = [
    ("Mumbai", "Maharashtra"), ("Delhi", "Delhi"), ("Bengaluru", "Karnataka"),
    ("Ahmedabad", "Gujarat"), ("Surat", "Gujarat"), ("Chennai", "Tamil Nadu"),
    ("Kolkata", "West Bengal"), ("Hyderabad", "Telangana"), ("Pune", "Maharashtra"),
    ("Jaipur", "Rajasthan"), ("Ludhiana", "Punjab"), ("Rajkot", "Gujarat"),
    ("Coimbatore", "Tamil Nadu"), ("Kanpur", "Uttar Pradesh"), ("Nagpur", "Maharashtra"),
    ("Indore", "Madhya Pradesh"), ("Thane", "Maharashtra"), ("Bhopal", "Madhya Pradesh"),
    ("Vadodara", "Gujarat"), ("Nashik", "Maharashtra"), ("Faridabad", "Haryana"),
    ("Meerut", "Uttar Pradesh"), ("Agra", "Uttar Pradesh"), ("Noida", "Uttar Pradesh"),
    ("Gurgaon", "Haryana"), ("Amritsar", "Punjab"), ("Visakhapatnam", "Andhra Pradesh"),
    ("Kochi", "Kerala"), ("Mysuru", "Karnataka"), ("Patna", "Bihar"),
]

SUPPLIER_SUFFIXES = [
    "Pvt Ltd", "Industries", "Enterprises", "Traders", "Manufacturers",
    "& Co.", "International", "Corporation", "Group", "Solutions",
    "Trading Co.", "Exports", "Impex", "Brothers",
]

SOURCES = ["IndiaMART", "TradeIndia"]

ADJECTIVES = [
    "Heavy Duty", "Industrial Grade", "High Performance", "Premium Quality",
    "Advanced", "Precision", "Automatic", "Semi-Automatic", "Electric",
    "Hydraulic", "Pneumatic", "Digital", "Smart", "Compact", "Portable",
]


def random_supplier(city):
    prefix = random.choice([
        "Bharat", "India", "Shree", "Sri", "National", "Global",
        "Modern", "New", "Pioneer", "Supreme", "Star", "Royal",
        "Excel", "Prime", "United",
    ])
    suffix = random.choice(SUPPLIER_SUFFIXES)
    return f"{prefix} {suffix}"


def random_price(lo, hi):
    base = random.uniform(lo, hi)
    # snap to clean numbers
    if base > 100000:
        base = round(base / 10000) * 10000
    elif base > 10000:
        base = round(base / 1000) * 1000
    elif base > 1000:
        base = round(base / 100) * 100
    else:
        base = round(base / 10) * 10
    spread = random.uniform(0, 0.3)
    return base, round(base * (1 + spread))


def generate_products(n_per_category: int = 80) -> list[dict]:
    products = []
    sources_cycle = SOURCES * 50

    for cat, meta in CATEGORIES.items():
        for i in range(n_per_category):
            city, state = random.choice(INDIAN_CITIES)
            supplier = random_supplier(city)
            prod_base = random.choice(meta["products"])
            adj = random.choice(ADJECTIVES) if random.random() > 0.4 else ""
            title = f"{adj} {prod_base}".strip()

            lo, hi = meta["price_range"]
            p_min, p_max = random_price(lo, hi)
            unit = random.choice(meta["units"])
            moq = random.choice(meta["moq"])
            source = random.choice(SOURCES)

            # Simulate rating / review
            has_rating = random.random() > 0.35
            rating = round(random.uniform(3.2, 5.0), 1) if has_rating else None
            reviews = random.randint(2, 420) if has_rating else 0
            verified = random.random() > 0.45

            # Simulate dates spread over last 90 days
            days_ago = random.randint(0, 90)
            scraped = (datetime.utcnow() - timedelta(days=days_ago)).isoformat()

            keywords = list(set([w.lower() for w in re.findall(r"\b[a-zA-Z]{4,}\b", title)]))[:6]

            uid = hashlib.md5(f"{source}:{cat}:{title}:{supplier}:{i}".encode()).hexdigest()[:12]
            url_slug = title.lower().replace(" ", "-").replace("/", "")
            source_url = f"https://www.{'indiamart' if source == 'IndiaMART' else 'tradeindia'}.com/products/{url_slug}-{uid}.html"

            products.append({
                "id": uid,
                "title": title,
                "category": cat,
                "subcategory": prod_base,
                "price_raw": f"₹{p_min:,.0f} - ₹{p_max:,.0f} per {unit}",
                "price_min": p_min,
                "price_max": p_max,
                "price_unit": unit,
                "currency": "INR",
                "supplier_name": supplier,
                "supplier_location": f"{city}, {state}",
                "supplier_city": city,
                "supplier_state": state,
                "supplier_country": "India",
                "min_order_qty": moq,
                "description": f"Quality {title} available from {supplier}, {city}.",
                "keywords": ",".join(keywords),
                "source": source,
                "source_url": source_url,
                "scraped_at": scraped,
                "verified_supplier": verified,
                "rating": rating,
                "review_count": reviews,
            })

    random.shuffle(products)
    return products


import re


def save_dataset(output_dir: str = "data", n_per_category: int = 80):
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    products = generate_products(n_per_category)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = f"{output_dir}/products_synthetic_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

    csv_path = f"{output_dir}/products_synthetic_{ts}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=products[0].keys())
        writer.writeheader()
        writer.writerows(products)

    print(f"Generated {len(products)} synthetic products")
    print(f"  JSON → {json_path}")
    print(f"  CSV  → {csv_path}")
    return json_path, csv_path, products


if __name__ == "__main__":
    save_dataset("data", n_per_category=80)
