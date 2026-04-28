#!/usr/bin/env python3
"""
B2B Market Intelligence — Main Runner
Stages: 1) Scrape (live or synthetic) → 2) ETL → 3) EDA → 4) HTML Report
"""

import argparse
import sys
import os
import glob
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def stage_scrape(live: bool, pages: int):
    logger.info("=" * 60)
    logger.info("STAGE 1 — DATA COLLECTION")
    logger.info("=" * 60)
    if live:
        logger.info("Mode: LIVE (real HTTP requests to IndiaMART / TradeIndia)")
        from crawler.crawler import CrawlerOrchestrator
        orch = CrawlerOrchestrator(output_dir="data")
        orch.run(max_pages_per_cat=pages)
        json_path, csv_path = orch.save()
    else:
        logger.info("Mode: SYNTHETIC (demo data — no network required)")
        from crawler.synthetic_data import save_dataset
        json_path, csv_path, _ = save_dataset(output_dir="data", n_per_category=80)
    return json_path


def stage_etl(raw_path: str) -> "pd.DataFrame":
    logger.info("\n" + "=" * 60)
    logger.info("STAGE 2 — ETL / CLEANING")
    logger.info("=" * 60)
    import sys
    sys.path.insert(0, str(ROOT))
    from etl.pipeline import run_etl
    return run_etl(raw_path, output_dir="data")


def stage_eda(df) -> dict:
    logger.info("\n" + "=" * 60)
    logger.info("STAGE 3 — EXPLORATORY DATA ANALYSIS")
    logger.info("=" * 60)
    from eda.analysis import run_eda
    return run_eda(df, output_dir="output")


def stage_report(df, eda_result: dict):
    logger.info("\n" + "=" * 60)
    logger.info("STAGE 4 — HTML REPORT")
    logger.info("=" * 60)
    from report.html_report import generate_report
    path = generate_report(df, eda_result, output_path="output/report.html")
    logger.info(f"Report → {path}")
    return path


def main():
    parser = argparse.ArgumentParser(
        description="B2B Market Intelligence Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                   # Run with synthetic data (no network)
  python main.py --live            # Run with live scraping
  python main.py --live --pages 3  # Live scraping, 3 pages per category
  python main.py --skip-scrape     # Re-use latest scraped data
        """
    )
    parser.add_argument("--live", action="store_true",
                        help="Use live scraper instead of synthetic data")
    parser.add_argument("--pages", type=int, default=2,
                        help="Pages per category (live mode only, default 2)")
    parser.add_argument("--skip-scrape", action="store_true",
                        help="Skip scraping, use most recent data file")
    args = parser.parse_args()

    Path("data").mkdir(exist_ok=True)
    Path("output").mkdir(exist_ok=True)

    # Stage 1
    if args.skip_scrape:
        files = (
            sorted(glob.glob("data/clean_products_*.json")) or
            sorted(glob.glob("data/products_synthetic_*.json")) or
            sorted(glob.glob("data/products_*.json"))
        )
        if not files:
            logger.error("No data files found. Run without --skip-scrape first.")
            sys.exit(1)
        raw_path = files[-1]
        logger.info(f"Using existing file: {raw_path}")
    else:
        raw_path = stage_scrape(live=args.live, pages=args.pages)

    # Stage 2
    df = stage_etl(raw_path)

    # Stage 3
    eda_result = stage_eda(df)

    # Stage 4
    report_path = stage_report(df, eda_result)

    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"  Rows processed : {len(df)}")
    logger.info(f"  Charts generated: {len(eda_result.get('charts', {}))}")
    logger.info(f"  Report         : {report_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
