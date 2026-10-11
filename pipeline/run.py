"""Pipeline entry point:   python -m pipeline.run --raw-dir data/raw

Steps (each one logged; any failure stops the run with a non-zero exit code):
  1. validate_inputs            all files + expected columns present?  (no DB changes yet)
  2. load_raw                   CSV -> raw_* tables, rebuilt atomically per table
  3. transform_and_quality_gate staging + marts + data-quality checks in ONE transaction;
                                a failed check ROLLS BACK the rebuild (the alarm)
  4. analysis_queries           sql/analysis/*.sql -> outputs/query_results/*.csv

Exit codes: 0 ok | 2 bad input files | 3 data-quality alarm | 1 anything else
"""
import argparse
import logging
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import ingest, quality, queries
from .config import (DEFAULT_DB_PATH, DEFAULT_RAW_DIR, LOG_DIR, OUTPUT_DIR,
                     SQL_DIR, SYNTHETIC_MARKER)
from .db import connect, run_sql_dir, table_counts, transaction
from .errors import DataQualityError, PipelineError

log = logging.getLogger("pipeline")


def configure_logging(log_dir=LOG_DIR, level="INFO"):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for h in list(root.handlers):          # avoid duplicate handlers on repeated calls
        root.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)-17s | %(message)s")
    for handler in (logging.StreamHandler(sys.stdout),
                    logging.FileHandler(Path(log_dir) / "pipeline.log", encoding="utf-8")):
        handler.setFormatter(fmt)
        root.addHandler(handler)
    root.setLevel(level)


@contextmanager
def step(name):
    """Log START / DONE (with timing) or FAILED for one pipeline step."""
    log.info("START  %s", name)
    t0 = time.perf_counter()
    try:
        yield
    except Exception as exc:
        log.error("FAILED %s after %.1fs: %s", name, time.perf_counter() - t0,
                  str(exc).splitlines()[0] if str(exc) else type(exc).__name__)
        raise
    log.info("DONE   %s in %.1fs", name, time.perf_counter() - t0)


def _log_run(conn, run_id, started, status, message, source_label):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS etl_run_log (run_id TEXT PRIMARY KEY, started_at TEXT, "
        "finished_at TEXT, status TEXT, message TEXT, data_source TEXT)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO etl_run_log VALUES (?,?,?,?,?,?)",
        (run_id, started, datetime.now(timezone.utc).isoformat(timespec="seconds"),
         status, message, source_label),
    )


def run_pipeline(raw_dir=DEFAULT_RAW_DIR, db_path=DEFAULT_DB_PATH,
                 output_dir=OUTPUT_DIR, run_queries=True):
    raw_dir, db_path = Path(raw_dir), Path(db_path)
    run_id = uuid.uuid4().hex[:12]
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source_label = ("SYNTHETIC DEMO DATA" if (raw_dir / SYNTHETIC_MARKER).exists()
                    else "Olist (real data)")
    log.info("run %s | raw=%s | db=%s | source=%s", run_id, raw_dir, db_path, source_label)

    with step("validate_inputs"):
        headers = ingest.validate_sources(raw_dir)

    conn = connect(db_path)
    try:
        with step("load_raw"):
            ingest.load_all(conn, raw_dir, headers)

        with step("transform_and_quality_gate"):
            checks = quality.load_checks(SQL_DIR / "dq")
            results = None
            try:
                with transaction(conn):
                    run_sql_dir(conn, SQL_DIR / "staging")
                    run_sql_dir(conn, SQL_DIR / "marts")
                    results = quality.run_checks(conn, checks)
                    quality.assert_all_passed(results)
            except DataQualityError:
                # transaction rolled back -> old staging/marts are intact
                quality.save_results(conn, run_id, results)
                raise
            quality.save_results(conn, run_id, results)
            for name, n in table_counts(conn).items():
                log.info("table %-28s %9d rows", name, n)

        if run_queries:
            with step("analysis_queries"):
                queries.run_all(conn, output_dir)

        _log_run(conn, run_id, started, "SUCCESS", "ok", source_label)
    except Exception as exc:
        _log_run(conn, run_id, started, "FAILED", str(exc)[:500], source_label)
        raise
    finally:
        conn.close()
    log.info("pipeline finished OK (run %s)", run_id)
    return run_id


def main(argv=None):
    p = argparse.ArgumentParser(description="Olist ELT pipeline")
    p.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    p.add_argument("--db", default=str(DEFAULT_DB_PATH))
    p.add_argument("--output-dir", default=str(OUTPUT_DIR))
    p.add_argument("--skip-queries", action="store_true")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)
    configure_logging(level=args.log_level)
    try:
        run_pipeline(args.raw_dir, args.db, args.output_dir, not args.skip_queries)
    except PipelineError as exc:
        log.error("PIPELINE STOPPED: %s", exc)
        print(f"\nPIPELINE STOPPED: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception:
        log.exception("unexpected failure")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
