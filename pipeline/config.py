"""Paths and the description of the nine source files.

`required_columns` is the contract with the upstream data: if one of these is
missing from a CSV header the pipeline stops before touching the database.
Extra columns are allowed (they are loaded into the raw table and ignored later).
"""
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = PROJECT_ROOT / "sql"
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "olist.db"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
LOG_DIR = PROJECT_ROOT / "logs"

# Dropped into the raw folder by tools/make_synthetic_data.py so that reports
# built from fake data can never be mistaken for the real thing.
SYNTHETIC_MARKER = "SYNTHETIC_DATA.txt"


@dataclass(frozen=True)
class SourceSpec:
    file_name: str
    table: str
    required_columns: tuple


SOURCES = (
    SourceSpec(
        "olist_customers_dataset.csv",
        "raw_customers",
        ("customer_id", "customer_unique_id", "customer_zip_code_prefix",
         "customer_city", "customer_state"),
    ),
    SourceSpec(
        "olist_orders_dataset.csv",
        "raw_orders",
        ("order_id", "customer_id", "order_status", "order_purchase_timestamp",
         "order_approved_at", "order_delivered_carrier_date",
         "order_delivered_customer_date", "order_estimated_delivery_date"),
    ),
    SourceSpec(
        "olist_order_items_dataset.csv",
        "raw_order_items",
        ("order_id", "order_item_id", "product_id", "seller_id",
         "shipping_limit_date", "price", "freight_value"),
    ),
    SourceSpec(
        "olist_order_payments_dataset.csv",
        "raw_order_payments",
        ("order_id", "payment_sequential", "payment_type",
         "payment_installments", "payment_value"),
    ),
    SourceSpec(
        "olist_order_reviews_dataset.csv",
        "raw_order_reviews",
        ("review_id", "order_id", "review_score", "review_comment_title",
         "review_comment_message", "review_creation_date",
         "review_answer_timestamp"),
    ),
    SourceSpec(
        "olist_products_dataset.csv",
        "raw_products",
        ("product_id", "product_category_name"),
    ),
    SourceSpec(
        "olist_sellers_dataset.csv",
        "raw_sellers",
        ("seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"),
    ),
    SourceSpec(
        "olist_geolocation_dataset.csv",
        "raw_geolocation",
        ("geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng",
         "geolocation_city", "geolocation_state"),
    ),
    SourceSpec(
        "product_category_name_translation.csv",
        "raw_product_category_translation",
        ("product_category_name", "product_category_name_english"),
    ),
)
