"""Airflow DAG (bonus): run the Olist pipeline every day.

    validate_inputs >> load_raw >> transform_and_quality_gate >> analysis_queries

Each task calls the same functions the CLI uses, so behaviour is identical.
Input and data-quality failures raise AirflowFailException: retrying cannot fix a
missing file or a bad batch, so the task fails immediately and the DAG run is red.

Configuration through environment variables (defaults point at the repo folders):
    OLIST_PROJECT_DIR   path to this repository
    OLIST_RAW_DIR       folder with the Olist CSVs
    OLIST_DB_PATH       SQLite database file
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("OLIST_PROJECT_DIR", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(PROJECT_DIR))

try:                                         # Airflow 3
    from airflow.sdk import DAG, task
    from airflow.exceptions import AirflowFailException
except ImportError:                          # Airflow 2.x
    from airflow import DAG
    from airflow.decorators import task
    from airflow.exceptions import AirflowFailException

RAW_DIR = Path(os.environ.get("OLIST_RAW_DIR", PROJECT_DIR / "data" / "raw"))
DB_PATH = Path(os.environ.get("OLIST_DB_PATH", PROJECT_DIR / "db" / "olist.db"))
OUT_DIR = PROJECT_DIR / "outputs"


def _fail_fast(exc):
    """Turn expected pipeline errors into non-retryable Airflow failures."""
    from pipeline.errors import PipelineError
    if isinstance(exc, PipelineError):
        raise AirflowFailException(str(exc)) from exc
    raise exc


with DAG(
    dag_id="olist_weekly_review_daily",
    description="Daily ELT + data-quality gate + analysis queries for the Olist marketplace",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,                  # the pipeline is a full refresh; past runs add nothing
    max_active_runs=1,              # never two writers on the same SQLite file
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["olist", "elt", "data-quality"],
) as dag:

    @task
    def validate_inputs():
        from pipeline import ingest
        try:
            ingest.validate_sources(RAW_DIR)
        except Exception as exc:
            _fail_fast(exc)

    @task
    def load_raw():
        from pipeline import ingest
        from pipeline.db import connect
        conn = connect(DB_PATH)
        try:
            headers = ingest.validate_sources(RAW_DIR)
            ingest.load_all(conn, RAW_DIR, headers)
        except Exception as exc:
            _fail_fast(exc)
        finally:
            conn.close()

    @task
    def transform_and_quality_gate(run_id: str = "airflow"):
        from pipeline import quality
        from pipeline.config import SQL_DIR
        from pipeline.db import connect, run_sql_dir, transaction
        from pipeline.errors import DataQualityError
        conn = connect(DB_PATH)
        results = None
        try:
            checks = quality.load_checks(SQL_DIR / "dq")
            try:
                with transaction(conn):            # rolled back if any check fails
                    run_sql_dir(conn, SQL_DIR / "staging")
                    run_sql_dir(conn, SQL_DIR / "marts")
                    results = quality.run_checks(conn, checks)
                    quality.assert_all_passed(results)
            except DataQualityError:
                quality.save_results(conn, run_id, results)
                raise
            quality.save_results(conn, run_id, results)
        except Exception as exc:
            _fail_fast(exc)
        finally:
            conn.close()

    @task
    def analysis_queries():
        from pipeline import queries
        from pipeline.db import connect
        conn = connect(DB_PATH)
        try:
            queries.run_all(conn, OUT_DIR)
        finally:
            conn.close()

    validate_inputs() >> load_raw() >> transform_and_quality_gate() >> analysis_queries()
