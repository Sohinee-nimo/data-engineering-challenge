# B2B Market Intelligence — Data Gathering & EDA

A complete data pipeline that collects, cleans, and analyses product listings
from Indian B2B marketplaces (IndiaMART, TradeIndia), with a rich HTML report.

---

## Project Structure

```
b2b-market-intel/
├── main.py                    # Master runner (all stages)
├── requirements.txt
│
├── crawler/
│   ├── crawler.py             # Live HTTP scraper (IndiaMART + TradeIndia)
│   └── synthetic_data.py      # Realistic synthetic data generator (demo / CI)
│
├── etl/
│   └── pipeline.py            # Cleaning, normalisation, deduplication, quality scoring
│
├── eda/
│   └── analysis.py            # 11 chart types + summary stats + insight generation
│
├── report/
│   └── html_report.py         # Self-contained HTML dashboard
│
├── data/                      # Auto-created: raw + clean data files (JSON/CSV)
└── output/
    ├── charts/                # 11 PNG charts
    ├── summary_stats.json
    ├── insights.json
    └── report.html            # ← Open this in your browser
```

---

## Quick Start

### 1. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run with synthetic data (no network required)

```bash
python3 main.py
```

### 3. Run with live scraping

```bash
python3 main.py --live
# or with more pages per category:
python3 main.py --live --pages 3
```

### 4. Skip scraping, re-run EDA on existing data

```bash
python3 main.py --skip-scrape
```

### 5. View the report

Open `output/report.html` in any web browser.

---

## Pipeline Stages

| Stage | Module | Description |
|-------|--------|-------------|
| 1 | `crawler/` | HTTP crawling with rate limiting, retry, rotating headers |
| 2 | `etl/` | Text cleaning, price normalisation, location parsing, quality scoring |
| 3 | `eda/` | 11 charts (distributions, heatmaps, keywords, ratings, quality) |
| 4 | `report/` | Self-contained HTML dashboard with embedded charts |

---

## Target Categories

| Category | Key Products |
|----------|-------------|
| **Industrial Machinery** | CNC machines, hydraulic presses, conveyors, pumps |
| **Electronics** | PCBs, sensors, controllers, inverters, drives |
| **Textiles** | Cotton fabrics, yarns, denim, sarees, threads |
| **Chemical** | Acids, solvents, resins, oxides, bicarbonates |
| **Agriculture** | Tractors, irrigation systems, harvesters, sprayers |

---

## Crawling Design

```
PoliteSession
├── Random delay between requests (2.5–6 sec)
├── Exponential backoff on 429/5xx (up to 3 retries)
├── Rotating User-Agent strings (4 modern browsers)
└── Respects HTTP 403/404 (no hammering blocked paths)

IndiaMARTCrawler     → indiamart.com/search.mp?ss=...
TradeIndiaCrawler    → tradeindia.com/search.html?search_text=...
CrawlerOrchestrator  → Runs both, deduplicates by hash(source+url+title)
```

---

## ETL Steps

1. **Load** — JSON or CSV
2. **Text clean** — strip whitespace, remove zero-width chars
3. **Deduplication** — by `id` then by `(title, supplier_name)`
4. **Price normalisation** — extract min/max from messy strings; IQR-cap outliers
5. **Location parsing** — split `"City, State"` strings; title-case normalisation
6. **Category inference** — keyword matching for uncategorised rows
7. **Quality scoring** — 0–100 score per row (price/supplier/location/title presence)
8. **Price buckets** — `< ₹1K` → `> ₹10L` categorical bands

---

## EDA Charts

| Chart | Insight |
|-------|---------|
| Category Distribution | Bar + pie of listing counts |
| Price Distributions | Per-category log-scale histograms |
| Price Boxplot | Cross-category range comparison |
| Top Supplier Cities | Bar of 20 most active cities |
| State × Category Heatmap | Geographic supply density |
| Source Comparison | Count / median price / verified % |
| Price Buckets | Stacked bar by bucket × category |
| Keyword Frequency | Top 30 product title words |
| Rating Distribution | Histogram + avg rating by category |
| Quality Analysis | Score distribution + missing value % |
| Scrape Timeline | Daily listing activity |

---

## Output Files

| File | Contents |
|------|----------|
| `data/products_synthetic_*.json` | Raw scraped data (JSON array) |
| `data/products_synthetic_*.csv` | Raw scraped data (CSV) |
| `data/clean_products_*.csv` | ETL-cleaned data |
| `output/charts/*.png` | 11 EDA chart images |
| `output/summary_stats.json` | Structured summary statistics |
| `output/insights.json` | Auto-generated text insights |
| `output/report.html` | Full interactive dashboard |

---

## Requirements

```
requests>=2.31
beautifulsoup4>=4.12
pandas>=2.0
numpy>=1.26
matplotlib>=3.8
seaborn>=0.13
```

Python 3.10+ recommended.

---

## Notes on Live Scraping

- Both target sites may require JavaScript rendering for some pages (Selenium/Playwright not included to keep dependencies minimal). The HTTP crawler handles static listing pages effectively.
- IndiaMART and TradeIndia are public B2B directories; scraping is intended for research/analysis only.
- Always respect `robots.txt` and the sites' terms of service in production use.

---

## License

MIT — free to use, modify, and distribute.
