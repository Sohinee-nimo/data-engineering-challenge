"""
B2B Marketplace Crawler
Targets: IndiaMART, TradeIndia, ExportersIndia (publicly accessible listing pages)
Strategy: Polite crawling with rate limiting, rotating headers, exponential backoff
"""

import time
import random
import logging
import json
import re
import hashlib
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict, field
from urllib.parse import urljoin, urlparse, quote_plus

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Data Model
# ──────────────────────────────────────────────

@dataclass
class Product:
    id: str = ""
    title: str = ""
    category: str = ""
    subcategory: str = ""
    price_raw: str = ""
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    price_unit: str = ""
    currency: str = "INR"
    supplier_name: str = ""
    supplier_location: str = ""
    supplier_city: str = ""
    supplier_state: str = ""
    supplier_country: str = "India"
    min_order_qty: str = ""
    description: str = ""
    keywords: list = field(default_factory=list)
    source: str = ""
    source_url: str = ""
    scraped_at: str = ""
    verified_supplier: bool = False
    rating: Optional[float] = None
    review_count: int = 0

    def to_dict(self):
        d = asdict(self)
        d["keywords"] = ",".join(self.keywords)
        return d


# ──────────────────────────────────────────────
# HTTP Session with politeness controls
# ──────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]


class PoliteSession:
    """HTTP session with rate limiting, retries, and rotating headers."""

    def __init__(self, min_delay: float = 2.0, max_delay: float = 5.0):
        self.session = requests.Session()
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._last_request = 0.0

    def _headers(self):
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "DNT": "1",
        }

    def _wait(self):
        elapsed = time.time() - self._last_request
        delay = random.uniform(self.min_delay, self.max_delay)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request = time.time()

    def get(self, url: str, retries: int = 3, timeout: int = 15) -> Optional[requests.Response]:
        self._wait()
        for attempt in range(retries):
            try:
                resp = self.session.get(url, headers=self._headers(), timeout=timeout)
                if resp.status_code == 200:
                    return resp
                elif resp.status_code == 429:
                    wait = (2 ** attempt) * 10
                    logger.warning(f"Rate limited. Waiting {wait}s …")
                    time.sleep(wait)
                elif resp.status_code in (403, 404):
                    logger.warning(f"HTTP {resp.status_code} for {url}")
                    return None
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt+1} failed: {e}")
                time.sleep(2 ** attempt)
        return None


# ──────────────────────────────────────────────
# Price parser helper
# ──────────────────────────────────────────────

def parse_price(raw: str):
    """Extract min/max price and unit from messy price strings."""
    if not raw:
        return None, None, ""
    raw = raw.strip()
    unit_match = re.search(r"(?:per|/)\s*(.+)", raw, re.IGNORECASE)
    unit = unit_match.group(1).strip() if unit_match else ""

    numbers = re.findall(r"[\d,]+(?:\.\d+)?", raw.replace(",", ""))
    floats = []
    for n in numbers:
        try:
            floats.append(float(n.replace(",", "")))
        except ValueError:
            pass
    if len(floats) >= 2:
        return min(floats), max(floats), unit
    elif len(floats) == 1:
        return floats[0], floats[0], unit
    return None, None, unit


def make_id(source: str, url: str, title: str) -> str:
    key = f"{source}:{url}:{title}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


# ──────────────────────────────────────────────
# IndiaMART Crawler
# ──────────────────────────────────────────────

INDIAMART_CATEGORIES = {
    "Industrial Machinery": "https://www.indiamart.com/proddir/industrial-machinery.html",
    "Electronics": "https://www.indiamart.com/proddir/electronics.html",
    "Textiles": "https://www.indiamart.com/proddir/textiles.html",
    "Chemical": "https://www.indiamart.com/proddir/chemicals.html",
    "Agriculture": "https://www.indiamart.com/proddir/agriculture-products.html",
}

INDIAMART_SEARCH_URLS = {
    "Industrial Machinery": "https://www.indiamart.com/search.mp?ss=industrial+machinery",
    "Electronics": "https://www.indiamart.com/search.mp?ss=electronics+components",
    "Textiles": "https://www.indiamart.com/search.mp?ss=textile+fabric",
    "Chemical": "https://www.indiamart.com/search.mp?ss=industrial+chemicals",
    "Agriculture": "https://www.indiamart.com/search.mp?ss=agriculture+equipment",
}


class IndiaMARTCrawler:
    SOURCE = "IndiaMART"
    BASE = "https://www.indiamart.com"

    def __init__(self, session: PoliteSession):
        self.session = session

    def crawl_category(self, category: str, url: str, max_pages: int = 3) -> list[Product]:
        products = []
        for page in range(1, max_pages + 1):
            page_url = f"{url}&page={page}" if "?" in url else f"{url}?page={page}"
            logger.info(f"[IndiaMART] {category} — page {page}: {page_url}")
            resp = self.session.get(page_url)
            if not resp:
                break
            page_products = self._parse_search_page(resp.text, category, page_url)
            if not page_products:
                break
            products.extend(page_products)
            logger.info(f"  → {len(page_products)} products found")
        return products

    def _parse_search_page(self, html: str, category: str, url: str) -> list[Product]:
        soup = BeautifulSoup(html, "html.parser")
        products = []
        now = datetime.utcnow().isoformat()

        # IndiaMART search result cards
        selectors = [
            "div.srpPrdc",          # search result product card
            "div.product-list-item",
            "li.srp-product",
            "div[class*='product-card']",
            "div.srp-imp-list",
        ]
        cards = []
        for sel in selectors:
            cards = soup.select(sel)
            if cards:
                break

        # Fallback: generic product blocks
        if not cards:
            cards = soup.find_all("div", class_=re.compile(r"product|item|listing", re.I))

        for card in cards[:20]:
            try:
                p = self._parse_card(card, category, url, now)
                if p and p.title:
                    products.append(p)
            except Exception as e:
                logger.debug(f"Card parse error: {e}")
        return products

    def _parse_card(self, card, category, url, now) -> Optional[Product]:
        # Title
        title_el = card.find(["h2", "h3", "a"], class_=re.compile(r"title|name|prod", re.I))
        if not title_el:
            title_el = card.find(["h2", "h3"])
        title = title_el.get_text(strip=True) if title_el else ""
        if not title or len(title) < 3:
            return None

        # Price
        price_el = card.find(class_=re.compile(r"price|rate|cost", re.I))
        price_raw = price_el.get_text(strip=True) if price_el else ""
        p_min, p_max, p_unit = parse_price(price_raw)

        # Supplier
        sup_el = card.find(class_=re.compile(r"company|supplier|seller|comp", re.I))
        supplier = sup_el.get_text(strip=True) if sup_el else ""

        # Location
        loc_el = card.find(class_=re.compile(r"location|city|place|addr", re.I))
        location = loc_el.get_text(strip=True) if loc_el else ""
        city, state = self._split_location(location)

        # MOQ
        moq_el = card.find(string=re.compile(r"min.*order|moq", re.I))
        moq = moq_el.strip() if moq_el else ""

        # Link
        link_el = card.find("a", href=True)
        link = urljoin(self.BASE, link_el["href"]) if link_el else url

        # Keywords from title
        keywords = [w.lower() for w in re.findall(r"\b[a-zA-Z]{4,}\b", title)][:8]

        return Product(
            id=make_id(self.SOURCE, link, title),
            title=title,
            category=category,
            price_raw=price_raw,
            price_min=p_min,
            price_max=p_max,
            price_unit=p_unit,
            currency="INR",
            supplier_name=supplier,
            supplier_location=location,
            supplier_city=city,
            supplier_state=state,
            min_order_qty=moq,
            keywords=keywords,
            source=self.SOURCE,
            source_url=link,
            scraped_at=now,
        )

    def _split_location(self, loc: str):
        parts = [p.strip() for p in re.split(r"[,|]", loc) if p.strip()]
        city = parts[0] if parts else ""
        state = parts[1] if len(parts) > 1 else ""
        return city, state


# ──────────────────────────────────────────────
# TradeIndia Crawler (backup source)
# ──────────────────────────────────────────────

TRADEINDIA_SEARCH = {
    "Industrial Machinery": "https://www.tradeindia.com/search.html?search_text=industrial+machinery",
    "Electronics": "https://www.tradeindia.com/search.html?search_text=electronic+components",
    "Textiles": "https://www.tradeindia.com/search.html?search_text=textile+fabric",
    "Chemical": "https://www.tradeindia.com/search.html?search_text=industrial+chemicals",
    "Agriculture": "https://www.tradeindia.com/search.html?search_text=agriculture+machinery",
}


class TradeIndiaCrawler:
    SOURCE = "TradeIndia"
    BASE = "https://www.tradeindia.com"

    def __init__(self, session: PoliteSession):
        self.session = session

    def crawl_category(self, category: str, url: str, max_pages: int = 2) -> list[Product]:
        products = []
        for page in range(1, max_pages + 1):
            page_url = f"{url}&page={page}"
            logger.info(f"[TradeIndia] {category} — page {page}")
            resp = self.session.get(page_url)
            if not resp:
                break
            parsed = self._parse_page(resp.text, category, page_url)
            if not parsed:
                break
            products.extend(parsed)
            logger.info(f"  → {len(parsed)} products")
        return products

    def _parse_page(self, html: str, category: str, url: str) -> list[Product]:
        soup = BeautifulSoup(html, "html.parser")
        products = []
        now = datetime.utcnow().isoformat()

        cards = soup.select("div.product-listing, li.product, div[class*='listing']")
        if not cards:
            cards = soup.find_all("div", class_=re.compile(r"product|listing|item", re.I))

        for card in cards[:15]:
            try:
                title_el = card.find(["h2", "h3", "h4", "a"])
                title = title_el.get_text(strip=True) if title_el else ""
                if not title or len(title) < 3:
                    continue

                price_el = card.find(string=re.compile(r"₹|INR|Rs\.?|\$", re.I))
                price_raw = price_el.strip() if price_el else ""
                p_min, p_max, p_unit = parse_price(price_raw)

                loc_el = card.find(class_=re.compile(r"location|city", re.I))
                location = loc_el.get_text(strip=True) if loc_el else ""
                parts = [p.strip() for p in location.split(",") if p.strip()]
                city = parts[0] if parts else ""
                state = parts[1] if len(parts) > 1 else ""

                sup_el = card.find(class_=re.compile(r"company|supplier", re.I))
                supplier = sup_el.get_text(strip=True) if sup_el else ""

                link_el = card.find("a", href=True)
                link = urljoin(self.BASE, link_el["href"]) if link_el else url
                keywords = [w.lower() for w in re.findall(r"\b[a-zA-Z]{4,}\b", title)][:8]

                products.append(Product(
                    id=make_id(self.SOURCE, link, title),
                    title=title,
                    category=category,
                    price_raw=price_raw,
                    price_min=p_min,
                    price_max=p_max,
                    price_unit=p_unit,
                    currency="INR",
                    supplier_name=supplier,
                    supplier_location=location,
                    supplier_city=city,
                    supplier_state=state,
                    keywords=keywords,
                    source=self.SOURCE,
                    source_url=link,
                    scraped_at=now,
                ))
            except Exception as e:
                logger.debug(f"Parse error: {e}")
        return products


# ──────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────

class CrawlerOrchestrator:
    def __init__(self, output_dir: str = "data"):
        self.output_dir = output_dir
        self.session = PoliteSession(min_delay=2.5, max_delay=6.0)
        self.im_crawler = IndiaMARTCrawler(self.session)
        self.ti_crawler = TradeIndiaCrawler(self.session)
        self.all_products: list[Product] = []

    def run(self, max_pages_per_cat: int = 2):
        logger.info("=" * 60)
        logger.info("B2B Marketplace Crawler starting …")
        logger.info("=" * 60)

        # IndiaMART
        for cat, url in INDIAMART_SEARCH_URLS.items():
            try:
                prods = self.im_crawler.crawl_category(cat, url, max_pages=max_pages_per_cat)
                self.all_products.extend(prods)
            except Exception as e:
                logger.error(f"IndiaMART {cat} failed: {e}")

        # TradeIndia
        for cat, url in TRADEINDIA_SEARCH.items():
            try:
                prods = self.ti_crawler.crawl_category(cat, url, max_pages=max_pages_per_cat)
                self.all_products.extend(prods)
            except Exception as e:
                logger.error(f"TradeIndia {cat} failed: {e}")

        # Deduplicate by ID
        seen = set()
        unique = []
        for p in self.all_products:
            if p.id not in seen:
                seen.add(p.id)
                unique.append(p)
        self.all_products = unique

        logger.info(f"\nTotal unique products scraped: {len(self.all_products)}")
        return self.all_products

    def save(self):
        import os, csv
        os.makedirs(self.output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # JSON
        json_path = f"{self.output_dir}/products_{ts}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in self.all_products], f, indent=2, ensure_ascii=False)

        # CSV
        csv_path = f"{self.output_dir}/products_{ts}.csv"
        if self.all_products:
            rows = [p.to_dict() for p in self.all_products]
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

        logger.info(f"Saved JSON → {json_path}")
        logger.info(f"Saved CSV  → {csv_path}")
        return json_path, csv_path


if __name__ == "__main__":
    orch = CrawlerOrchestrator(output_dir="data")
    orch.run(max_pages_per_cat=2)
    orch.save()
