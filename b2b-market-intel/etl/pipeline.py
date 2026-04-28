"""
ETL Pipeline for B2B Marketplace Data
Handles: loading, cleaning, normalisation, deduplication, enrichment, validation
"""

import json
import re
import os
import csv
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── Constants ────────────────────────────────────────────────────────────────

KNOWN_CITIES = {
    "mumbai", "delhi", "bengaluru", "bangalore", "ahmedabad", "surat",
    "chennai", "kolkata", "hyderabad", "pune", "jaipur", "ludhiana",
    "rajkot", "coimbatore", "kanpur", "nagpur", "indore", "thane",
    "vadodara", "nashik", "faridabad", "meerut", "agra", "noida",
    "gurgaon", "gurugram", "amritsar", "visakhapatnam", "kochi", "mysuru",
    "patna", "bhopal",
}

KNOWN_STATES = {
    "maharashtra", "delhi", "karnataka", "gujarat", "tamil nadu",
    "west bengal", "telangana", "rajasthan", "punjab", "uttar pradesh",
    "madhya pradesh", "haryana", "andhra pradesh", "kerala", "bihar",
}

PRICE_KEYWORDS_TO_DROP = {"price on request", "call for price", "get latest price", "n/a", "-"}

CATEGORY_KEYWORDS = {
    "Industrial Machinery": ["machine", "machinery", "press", "conveyor", "pump",
                              "compressor", "boiler", "crane", "mill", "lathe"],
    "Electronics": ["sensor", "pcb", "controller", "inverter", "drive", "ups",
                     "transformer", "motor", "circuit", "board"],
    "Textiles": ["fabric", "yarn", "cloth", "saree", "cotton", "polyester",
                  "silk", "linen", "jute", "denim", "towel"],
    "Chemical": ["acid", "hydroxide", "carbonate", "solvent", "resin",
                  "oxide", "chloride", "sulphate", "ammonia", "peroxide"],
    "Agriculture": ["tractor", "seed", "irrigation", "harvester", "thresher",
                     "sprayer", "plough", "pump", "farm", "agro"],
}


# ── Loader ───────────────────────────────────────────────────────────────────

def load_raw(path: str) -> pd.DataFrame:
    """Load JSON or CSV into a DataFrame."""
    p = Path(path)
    if p.suffix == ".json":
        with open(p) as f:
            data = json.load(f)
        df = pd.DataFrame(data)
    elif p.suffix == ".csv":
        df = pd.read_csv(p)
    else:
        raise ValueError(f"Unsupported file type: {p.suffix}")
    logger.info(f"Loaded {len(df)} rows from {path}")
    return df


# ── Cleaning ─────────────────────────────────────────────────────────────────

def clean_text(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("\u00a0", " ").replace("\u200b", "")
    return s


def normalize_price(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure price_min / price_max are numeric; compute price_avg."""
    df["price_min"] = pd.to_numeric(df["price_min"], errors="coerce")
    df["price_max"] = pd.to_numeric(df["price_max"], errors="coerce")

    # If only one side exists, mirror it
    df["price_min"] = df["price_min"].fillna(df["price_max"])
    df["price_max"] = df["price_max"].fillna(df["price_min"])

    df["price_avg"] = (df["price_min"] + df["price_max"]) / 2

    # Cap extreme outliers per category using IQR
    for cat in df["category"].unique():
        mask = df["category"] == cat
        q1 = df.loc[mask, "price_avg"].quantile(0.05)
        q99 = df.loc[mask, "price_avg"].quantile(0.99)
        outlier = mask & ((df["price_avg"] < q1) | (df["price_avg"] > q99 * 10))
        df.loc[outlier, ["price_min", "price_max", "price_avg"]] = np.nan

    return df


def normalize_location(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize city/state; fix capitalisation."""
    df["supplier_city"] = df["supplier_city"].apply(lambda x: clean_text(str(x)).title() if pd.notna(x) else "")
    df["supplier_state"] = df["supplier_state"].apply(lambda x: clean_text(str(x)).title() if pd.notna(x) else "")

    # Fill city from supplier_location if blank
    def extract_city(row):
        if row["supplier_city"]:
            return row["supplier_city"]
        loc = clean_text(str(row.get("supplier_location", "")))
        parts = [p.strip() for p in loc.split(",") if p.strip()]
        return parts[0].title() if parts else ""

    def extract_state(row):
        if row["supplier_state"]:
            return row["supplier_state"]
        loc = clean_text(str(row.get("supplier_location", "")))
        parts = [p.strip() for p in loc.split(",") if p.strip()]
        return parts[1].title() if len(parts) > 1 else ""

    df["supplier_city"] = df.apply(extract_city, axis=1)
    df["supplier_state"] = df.apply(extract_state, axis=1)
    return df


def infer_category(title: str, existing: str) -> str:
    """If category is missing/unknown, infer from title keywords."""
    if existing and existing.strip() and existing not in ("Unknown", ""):
        return existing
    title_lower = title.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in title_lower for kw in kws):
            return cat
    return "Other"


def validate_row(row: pd.Series) -> dict:
    """Return a dict of quality flags."""
    flags = {
        "has_price": pd.notna(row.get("price_avg")) and row.get("price_avg", 0) > 0,
        "has_supplier": bool(str(row.get("supplier_name", "")).strip()),
        "has_location": bool(str(row.get("supplier_city", "")).strip()),
        "has_title": bool(str(row.get("title", "")).strip()),
        "price_suspicious": (
            pd.notna(row.get("price_min")) and
            pd.notna(row.get("price_max")) and
            row.get("price_max", 0) > row.get("price_min", 0) * 100
        ),
    }
    flags["quality_score"] = sum([
        flags["has_price"] * 30,
        flags["has_supplier"] * 25,
        flags["has_location"] * 25,
        flags["has_title"] * 20,
        -flags["price_suspicious"] * 10,
    ])
    return flags


# ── Main ETL ─────────────────────────────────────────────────────────────────

def run_etl(input_path: str, output_dir: str = "data") -> pd.DataFrame:
    logger.info(f"Starting ETL for: {input_path}")
    df = load_raw(input_path)
    raw_count = len(df)

    # ── 1. Text cleaning
    for col in ["title", "supplier_name", "supplier_location", "description"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_text)

    # ── 2. Deduplicate
    df = df.drop_duplicates(subset=["id"], keep="first")
    df = df.drop_duplicates(subset=["title", "supplier_name"], keep="first")
    logger.info(f"After dedup: {len(df)} rows (removed {raw_count - len(df)})")

    # ── 3. Normalise prices
    df = normalize_price(df)

    # ── 4. Normalise locations
    df = normalize_location(df)

    # ── 5. Category inference
    df["category"] = df.apply(
        lambda r: infer_category(str(r.get("title", "")), str(r.get("category", ""))), axis=1
    )

    # ── 6. Boolean normalisation
    if "verified_supplier" in df.columns:
        df["verified_supplier"] = df["verified_supplier"].astype(str).str.lower().isin(
            ["true", "1", "yes"]
        )

    # ── 7. Rating clamp
    if "rating" in df.columns:
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
        df["rating"] = df["rating"].clip(0, 5)

    # ── 8. Quality scoring
    quality_rows = df.apply(validate_row, axis=1)
    quality_df = pd.DataFrame(quality_rows.tolist(), index=df.index)
    df = pd.concat([df, quality_df], axis=1)

    # ── 9. Price bucket
    def price_bucket(p):
        if pd.isna(p):
            return "Unknown"
        if p < 1000:
            return "< ₹1K"
        elif p < 10000:
            return "₹1K–10K"
        elif p < 100000:
            return "₹10K–1L"
        elif p < 1000000:
            return "₹1L–10L"
        else:
            return "> ₹10L"

    df["price_bucket"] = df["price_avg"].apply(price_bucket)

    # ── 10. Save
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = f"{output_dir}/clean_products_{ts}.csv"
    out_json = f"{output_dir}/clean_products_{ts}.json"
    df.to_csv(out_csv, index=False)
    df.to_json(out_json, orient="records", indent=2, force_ascii=False)

    logger.info(f"ETL complete. Clean rows: {len(df)}")
    logger.info(f"  CSV  → {out_csv}")
    logger.info(f"  JSON → {out_json}")

    return df


if __name__ == "__main__":
    import glob
    files = sorted(glob.glob("data/products_synthetic_*.json"))
    if files:
        run_etl(files[-1])
    else:
        print("No synthetic data found. Run crawler/synthetic_data.py first.")
