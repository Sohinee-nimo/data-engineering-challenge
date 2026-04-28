"""
Exploratory Data Analysis Engine
Generates: summary stats, distribution charts, regional maps, keyword clouds,
           price analysis, source comparison, quality report, and HTML dashboard.
"""

import json
import re
import os
import warnings
import logging
from pathlib import Path
from collections import Counter
from datetime import datetime

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import seaborn as sns

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── Palette ───────────────────────────────────────────────────────────────────

PALETTE = {
    "Industrial Machinery": "#E63946",
    "Electronics":          "#2196F3",
    "Textiles":             "#9C27B0",
    "Chemical":             "#FF9800",
    "Agriculture":          "#4CAF50",
    "Other":                "#607D8B",
}

CAT_COLORS = list(PALETTE.values())

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 120,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.facecolor": "#FAFAFA",
    "figure.facecolor": "white",
})


# ── Helpers ───────────────────────────────────────────────────────────────────

def savefig(fig, path: str):
    fig.savefig(path, bbox_inches="tight", dpi=130, facecolor="white")
    plt.close(fig)
    logger.info(f"  Chart → {path}")


def color_for(cat: str) -> str:
    return PALETTE.get(cat, "#607D8B")


# ── Individual chart functions ─────────────────────────────────────────────────

def chart_category_distribution(df: pd.DataFrame, out: str):
    counts = df["category"].value_counts()
    colors = [color_for(c) for c in counts.index]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Bar chart
    ax = axes[0]
    bars = ax.barh(counts.index, counts.values, color=colors, edgecolor="white", linewidth=0.5)
    ax.set_title("Products per Category", fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Count")
    for bar, val in zip(bars, counts.values):
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
                f"{val}", va="center", fontsize=9)
    ax.invert_yaxis()

    # Pie chart
    ax2 = axes[1]
    wedges, texts, autotexts = ax2.pie(
        counts.values, labels=counts.index, autopct="%1.1f%%",
        colors=colors, startangle=140, pctdistance=0.75,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5}
    )
    for t in autotexts:
        t.set_fontsize(8)
    ax2.set_title("Category Share", fontsize=14, fontweight="bold", pad=12)

    fig.suptitle("Category Distribution", fontsize=16, fontweight="bold", y=1.01)
    fig.tight_layout()
    savefig(fig, out)


def chart_price_distributions(df: pd.DataFrame, out: str):
    cats = df["category"].unique()
    n = len(cats)
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    axes = axes.flatten()

    for i, cat in enumerate(sorted(cats)):
        ax = axes[i]
        sub = df[df["category"] == cat]["price_avg"].dropna()
        if len(sub) < 5:
            ax.set_visible(False)
            continue

        log_vals = np.log10(sub.clip(lower=1))
        ax.hist(log_vals, bins=25, color=color_for(cat), alpha=0.85, edgecolor="white")

        med = sub.median()
        ax.axvline(np.log10(med), color="black", linestyle="--", linewidth=1.2,
                   label=f"Median ₹{med:,.0f}")
        ax.set_title(cat, fontsize=10, fontweight="bold")
        ax.set_xlabel("log₁₀(Price ₹)", fontsize=8)
        ax.set_ylabel("Count", fontsize=8)
        ax.legend(fontsize=7)

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle("Price Distributions by Category (log scale)", fontsize=15, fontweight="bold")
    fig.tight_layout()
    savefig(fig, out)


def chart_price_boxplot(df: pd.DataFrame, out: str):
    fig, ax = plt.subplots(figsize=(13, 6))
    cats = sorted(df["category"].unique())
    data_per_cat = [np.log10(df[df["category"] == c]["price_avg"].dropna().clip(lower=1)) for c in cats]
    colors = [color_for(c) for c in cats]

    bp = ax.boxplot(data_per_cat, patch_artist=True, notch=False,
                    medianprops={"color": "black", "linewidth": 2})
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)

    ax.set_xticklabels(cats, rotation=20, ha="right", fontsize=10)
    ax.set_ylabel("log₁₀(Average Price ₹)", fontsize=11)
    ax.set_title("Price Range Comparison Across Categories", fontsize=14, fontweight="bold")

    # Y-axis tick labels to readable prices
    yticks = ax.get_yticks()
    ax.set_yticklabels([f"₹{10**y:,.0f}" if 0 <= y <= 8 else "" for y in yticks], fontsize=8)

    fig.tight_layout()
    savefig(fig, out)


def chart_top_cities(df: pd.DataFrame, out: str):
    city_counts = df["supplier_city"].value_counts().head(20)
    colors = plt.cm.viridis(np.linspace(0.2, 0.85, len(city_counts)))

    fig, ax = plt.subplots(figsize=(12, 7))
    bars = ax.bar(city_counts.index, city_counts.values, color=colors, edgecolor="white", linewidth=0.5)
    ax.set_title("Top 20 Supplier Cities", fontsize=14, fontweight="bold")
    ax.set_xlabel("City")
    ax.set_ylabel("Number of Listings")
    ax.tick_params(axis="x", rotation=45)
    for bar, val in zip(bars, city_counts.values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                str(val), ha="center", fontsize=7.5)

    fig.tight_layout()
    savefig(fig, out)


def chart_state_heatmap(df: pd.DataFrame, out: str):
    state_cat = df.groupby(["supplier_state", "category"]).size().unstack(fill_value=0)
    if state_cat.empty:
        return

    # Keep top 15 states
    top_states = df["supplier_state"].value_counts().head(15).index
    state_cat = state_cat.loc[state_cat.index.isin(top_states)]

    fig, ax = plt.subplots(figsize=(13, 7))
    sns.heatmap(state_cat, cmap="YlOrRd", annot=True, fmt="d", linewidths=0.4,
                ax=ax, cbar_kws={"label": "Listing Count"})
    ax.set_title("Listings by State × Category", fontsize=14, fontweight="bold")
    ax.set_xlabel("Category")
    ax.set_ylabel("State")
    plt.xticks(rotation=25, ha="right")
    fig.tight_layout()
    savefig(fig, out)


def chart_source_comparison(df: pd.DataFrame, out: str):
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))

    # Count per source
    src_counts = df["source"].value_counts()
    axes[0].bar(src_counts.index, src_counts.values,
                color=["#E63946", "#2196F3", "#4CAF50"][:len(src_counts)],
                edgecolor="white")
    axes[0].set_title("Listings per Source", fontsize=11, fontweight="bold")
    axes[0].set_ylabel("Count")

    # Avg price per source
    src_price = df.groupby("source")["price_avg"].median()
    axes[1].bar(src_price.index, src_price.values,
                color=["#E63946", "#2196F3", "#4CAF50"][:len(src_price)],
                edgecolor="white")
    axes[1].set_title("Median Price by Source", fontsize=11, fontweight="bold")
    axes[1].set_ylabel("₹ (median)")
    axes[1].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"₹{x:,.0f}"))

    # Verified supplier % per source
    if "verified_supplier" in df.columns:
        ver = df.groupby("source")["verified_supplier"].mean() * 100
        bars = axes[2].bar(ver.index, ver.values,
                           color=["#E63946", "#2196F3", "#4CAF50"][:len(ver)],
                           edgecolor="white")
        axes[2].set_title("% Verified Suppliers", fontsize=11, fontweight="bold")
        axes[2].set_ylabel("%")
        axes[2].set_ylim(0, 105)
        for bar, val in zip(bars, ver.values):
            axes[2].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                         f"{val:.1f}%", ha="center", fontsize=9)
    else:
        axes[2].set_visible(False)

    fig.suptitle("Source Platform Comparison", fontsize=14, fontweight="bold")
    fig.tight_layout()
    savefig(fig, out)


def chart_price_bucket_stacked(df: pd.DataFrame, out: str):
    order = ["< ₹1K", "₹1K–10K", "₹10K–1L", "₹1L–10L", "> ₹10L", "Unknown"]
    bucket_cat = df.groupby(["category", "price_bucket"]).size().unstack(fill_value=0)
    bucket_cat = bucket_cat.reindex(columns=[c for c in order if c in bucket_cat.columns])

    fig, ax = plt.subplots(figsize=(12, 6))
    bucket_cat.plot(kind="bar", stacked=True, ax=ax,
                    colormap="tab10", edgecolor="white", linewidth=0.4)
    ax.set_title("Price Bucket Distribution by Category", fontsize=14, fontweight="bold")
    ax.set_xlabel("Category")
    ax.set_ylabel("Count")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(title="Price Range", bbox_to_anchor=(1.01, 1), loc="upper left")
    fig.tight_layout()
    savefig(fig, out)


def chart_keyword_freq(df: pd.DataFrame, out: str):
    all_kws = []
    for kws in df["keywords"].dropna():
        if isinstance(kws, str):
            all_kws.extend([k.strip().lower() for k in kws.split(",") if len(k.strip()) > 3])

    stop = {"with", "from", "that", "this", "have", "been", "will", "high", "also",
            "more", "very", "some", "your", "than", "into", "used", "unit", "grade",
            "quality", "industrial", "machine"}
    filtered = [k for k in all_kws if k not in stop]
    counts = Counter(filtered).most_common(30)

    words, freqs = zip(*counts)
    colors = plt.cm.plasma(np.linspace(0.1, 0.85, len(words)))

    fig, ax = plt.subplots(figsize=(13, 6))
    bars = ax.barh(words, freqs, color=colors, edgecolor="white")
    ax.invert_yaxis()
    ax.set_title("Top 30 Product Keywords", fontsize=14, fontweight="bold")
    ax.set_xlabel("Frequency")
    for bar, val in zip(bars, freqs):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=8)
    fig.tight_layout()
    savefig(fig, out)


def chart_rating_dist(df: pd.DataFrame, out: str):
    if "rating" not in df.columns:
        return
    rated = df["rating"].dropna()
    if len(rated) < 10:
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    axes[0].hist(rated, bins=20, color="#2196F3", alpha=0.85, edgecolor="white")
    axes[0].axvline(rated.mean(), color="red", linestyle="--", label=f"Mean {rated.mean():.2f}")
    axes[0].set_title("Rating Distribution", fontsize=12, fontweight="bold")
    axes[0].set_xlabel("Rating")
    axes[0].set_ylabel("Count")
    axes[0].legend()

    cat_rating = df.groupby("category")["rating"].mean().sort_values(ascending=False)
    colors = [color_for(c) for c in cat_rating.index]
    axes[1].barh(cat_rating.index, cat_rating.values, color=colors, edgecolor="white")
    axes[1].set_xlim(0, 5.5)
    axes[1].set_title("Avg Rating by Category", fontsize=12, fontweight="bold")
    axes[1].set_xlabel("Average Rating")
    for i, (cat, val) in enumerate(cat_rating.items()):
        axes[1].text(val + 0.05, i, f"{val:.2f}", va="center", fontsize=9)

    fig.suptitle("Supplier Ratings Analysis", fontsize=14, fontweight="bold")
    fig.tight_layout()
    savefig(fig, out)


def chart_quality_score(df: pd.DataFrame, out: str):
    if "quality_score" not in df.columns:
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    q = df["quality_score"]
    axes[0].hist(q, bins=20, color="#4CAF50", alpha=0.85, edgecolor="white")
    axes[0].axvline(q.mean(), color="red", linestyle="--", label=f"Mean {q.mean():.1f}")
    axes[0].set_title("Data Quality Score Distribution", fontsize=12, fontweight="bold")
    axes[0].set_xlabel("Quality Score (0–100)")
    axes[0].set_ylabel("Count")
    axes[0].legend()

    # Missing value heatmap
    miss_cols = ["price_avg", "supplier_name", "supplier_city", "rating", "min_order_qty"]
    miss_cols = [c for c in miss_cols if c in df.columns]
    miss_pct = df[miss_cols].isnull().mean() * 100
    bars = axes[1].bar(miss_pct.index, miss_pct.values,
                       color=plt.cm.Reds(miss_pct.values / 100 + 0.2),
                       edgecolor="white")
    axes[1].set_title("Missing Value % by Field", fontsize=12, fontweight="bold")
    axes[1].set_ylabel("% Missing")
    axes[1].tick_params(axis="x", rotation=30)
    for bar, val in zip(bars, miss_pct.values):
        axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                     f"{val:.1f}%", ha="center", fontsize=8)

    fig.suptitle("Data Quality Analysis", fontsize=14, fontweight="bold")
    fig.tight_layout()
    savefig(fig, out)


def chart_scrape_timeline(df: pd.DataFrame, out: str):
    if "scraped_at" not in df.columns:
        return

    df["scraped_date"] = pd.to_datetime(df["scraped_at"], errors="coerce").dt.date
    daily = df.groupby("scraped_date").size().reset_index(name="count")
    if daily.empty or len(daily) < 2:
        return

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(daily["scraped_date"], daily["count"], alpha=0.35, color="#2196F3")
    ax.plot(daily["scraped_date"], daily["count"], color="#2196F3", linewidth=1.5)
    ax.set_title("Listings Scraped Over Time", fontsize=13, fontweight="bold")
    ax.set_xlabel("Date")
    ax.set_ylabel("Listings")
    plt.xticks(rotation=30)
    fig.tight_layout()
    savefig(fig, out)


# ── Summary Stats ─────────────────────────────────────────────────────────────

def compute_summary(df: pd.DataFrame) -> dict:
    stats = {
        "total_products": len(df),
        "categories": int(df["category"].nunique()),
        "sources": df["source"].nunique() if "source" in df.columns else 0,
        "unique_cities": df["supplier_city"].nunique() if "supplier_city" in df.columns else 0,
        "unique_states": df["supplier_state"].nunique() if "supplier_state" in df.columns else 0,
        "products_with_price": int(df["price_avg"].notna().sum()),
        "pct_with_price": round(df["price_avg"].notna().mean() * 100, 1),
        "median_price_overall": round(df["price_avg"].median(), 2) if df["price_avg"].notna().any() else None,
        "verified_supplier_pct": round(df["verified_supplier"].mean() * 100, 1) if "verified_supplier" in df.columns else None,
        "avg_rating": round(df["rating"].mean(), 2) if "rating" in df.columns and df["rating"].notna().any() else None,
        "category_breakdown": df["category"].value_counts().to_dict(),
        "source_breakdown": df["source"].value_counts().to_dict() if "source" in df.columns else {},
        "top_cities": df["supplier_city"].value_counts().head(10).to_dict(),
        "top_states": df["supplier_state"].value_counts().head(10).to_dict(),
        "price_by_category": {
            cat: {
                "median": round(sub["price_avg"].median(), 2),
                "mean": round(sub["price_avg"].mean(), 2),
                "min": round(sub["price_avg"].min(), 2),
                "max": round(sub["price_avg"].max(), 2),
                "count": int(sub["price_avg"].notna().sum()),
            }
            for cat, sub in df.groupby("category")
            if sub["price_avg"].notna().any()
        },
    }
    return stats


# ── Insights ──────────────────────────────────────────────────────────────────

def generate_insights(df: pd.DataFrame, stats: dict) -> list[str]:
    insights = []

    # Dominant category
    top_cat = df["category"].value_counts().idxmax()
    top_count = df["category"].value_counts().max()
    insights.append(
        f"**{top_cat}** is the most listed category with {top_count} products "
        f"({top_count/len(df)*100:.1f}% of total listings)."
    )

    # Price spread
    if stats.get("price_by_category"):
        sorted_cats = sorted(stats["price_by_category"].items(), key=lambda x: x[1]["median"])
        cheapest = sorted_cats[0]
        priciest = sorted_cats[-1]
        insights.append(
            f"**{cheapest[0]}** has the lowest median price "
            f"(₹{cheapest[1]['median']:,.0f}), while **{priciest[0]}** "
            f"is the highest (₹{priciest[1]['median']:,.0f})."
        )

    # Top city
    if stats.get("top_cities"):
        top_city = list(stats["top_cities"].keys())[0]
        top_city_count = list(stats["top_cities"].values())[0]
        insights.append(
            f"**{top_city}** leads as the top supplier city with {top_city_count} listings."
        )

    # Verified
    if stats.get("verified_supplier_pct") is not None:
        vp = stats["verified_supplier_pct"]
        if vp > 60:
            insights.append(f"Supplier trust is high — {vp:.1f}% of suppliers are verified.")
        elif vp < 30:
            insights.append(f"Only {vp:.1f}% of suppliers are verified — indicating potential data quality risk.")
        else:
            insights.append(f"{vp:.1f}% of suppliers carry a verified badge.")

    # Missing price
    missing_price_pct = 100 - stats.get("pct_with_price", 0)
    if missing_price_pct > 20:
        insights.append(
            f"{missing_price_pct:.1f}% of listings have no price — "
            "common in B2B where pricing is negotiated."
        )

    # Rating
    if stats.get("avg_rating"):
        insights.append(f"Average supplier rating across the dataset is **{stats['avg_rating']:.2f}/5.0**.")

    # Source diversity
    if stats.get("source_breakdown") and len(stats["source_breakdown"]) > 1:
        dominant_src = max(stats["source_breakdown"], key=stats["source_breakdown"].get)
        insights.append(f"**{dominant_src}** contributes the most listings among all scraped sources.")

    return insights


# ── Master EDA runner ─────────────────────────────────────────────────────────

def run_eda(df: pd.DataFrame, output_dir: str = "output") -> dict:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    charts_dir = f"{output_dir}/charts"
    Path(charts_dir).mkdir(exist_ok=True)

    logger.info("Running EDA …")

    charts = {}

    def c(name, fn, *args):
        path = f"{charts_dir}/{name}.png"
        try:
            fn(*args, path)
            charts[name] = path
        except Exception as e:
            logger.warning(f"Chart '{name}' failed: {e}")

    c("01_category_dist",     chart_category_distribution, df)
    c("02_price_hist",        chart_price_distributions, df)
    c("03_price_boxplot",     chart_price_boxplot, df)
    c("04_top_cities",        chart_top_cities, df)
    c("05_state_heatmap",     chart_state_heatmap, df)
    c("06_source_comparison", chart_source_comparison, df)
    c("07_price_buckets",     chart_price_bucket_stacked, df)
    c("08_keywords",          chart_keyword_freq, df)
    c("09_ratings",           chart_rating_dist, df)
    c("10_quality",           chart_quality_score, df)
    c("11_timeline",          chart_scrape_timeline, df)

    stats = compute_summary(df)
    insights = generate_insights(df, stats)

    # Save stats
    stats_path = f"{output_dir}/summary_stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    logger.info(f"Summary stats → {stats_path}")

    insights_path = f"{output_dir}/insights.json"
    with open(insights_path, "w") as f:
        json.dump(insights, f, indent=2)

    return {"charts": charts, "stats": stats, "insights": insights}


if __name__ == "__main__":
    import glob, sys
    sys.path.insert(0, "..")
    files = sorted(glob.glob("data/clean_products_*.csv"))
    if not files:
        files = sorted(glob.glob("data/products_synthetic_*.csv"))
    if not files:
        print("No data found. Run ETL first.")
        sys.exit(1)

    df = pd.read_csv(files[-1])
    run_eda(df, output_dir="output")
    print("EDA complete. Check output/charts/")
