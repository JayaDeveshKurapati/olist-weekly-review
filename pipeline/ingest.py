"""Part A, step 1-2: validate the input files, then load them as raw tables.

Raw tables mirror the CSVs exactly (every column TEXT, nothing cleaned). All the
cleaning happens later in SQL, so raw is always a faithful copy of what we received.

Idempotency: each raw table is rebuilt inside one transaction
(DROP -> CREATE -> INSERT -> audit row). Running the load twice leaves exactly the
same rows as running it once.
"""
import csv
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import SOURCES
from .db import transaction
from .errors import InputDataError

log = logging.getLogger("pipeline.ingest")
BATCH_SIZE = 50_000


def _read_header(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        try:
            header = next(csv.reader(fh))
        except StopIteration:
            return []
    return [h.strip() for h in header]


def validate_sources(raw_dir):
    """Check *all* files and columns up front and report every problem at once.

    Returns {table_name: header_list}. Raises InputDataError before the database
    is touched, so a bad delivery can never leave a half-loaded warehouse.
    """
    raw_dir = Path(raw_dir)
    problems, headers = [], {}

    if not raw_dir.is_dir():
        raise InputDataError(
            f"Raw data folder not found: {raw_dir}. Download the Olist CSVs from "
            "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce and unzip "
            "them there (see README)."
        )

    for spec in SOURCES:
        path = raw_dir / spec.file_name
        if not path.is_file():
            problems.append(f"MISSING FILE   {spec.file_name}")
            continue
        header = _read_header(path)
        if not header:
            problems.append(f"EMPTY FILE     {spec.file_name} (no header row)")
            continue
        missing = [c for c in spec.required_columns if c not in header]
        if missing:
            problems.append(
                f"MISSING COLUMN {spec.file_name}: expected {missing} "
                f"but header is {header}"
            )
            continue
        extra = [c for c in header if c not in spec.required_columns]
        if extra:
            log.info("%s has extra columns %s (kept in raw, unused downstream)",
                     spec.file_name, extra)
        headers[spec.table] = header

    if problems:
        raise InputDataError(
            f"Input validation failed in {raw_dir}:\n  " + "\n  ".join(problems)
        )
    log.info("all %d source files present with the expected columns", len(SOURCES))
    return headers


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _load_one(conn, spec, path, header):
    n_cols = len(header)
    col_defs = ", ".join(f"{_quote(c)} TEXT" for c in header)
    insert_sql = (
        f"INSERT INTO {_quote(spec.table)} VALUES ({', '.join('?' * n_cols)})"
    )
    loaded = 0
    with transaction(conn):
        conn.execute(f"DROP TABLE IF EXISTS {_quote(spec.table)}")
        conn.execute(f"CREATE TABLE {_quote(spec.table)} ({col_defs})")
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            next(reader)  # header
            batch = []
            for row in reader:
                if not row:  # blank line
                    continue
                if len(row) != n_cols:
                    raise InputDataError(
                        f"{spec.file_name} line {reader.line_num}: expected "
                        f"{n_cols} fields, found {len(row)}"
                    )
                batch.append(row)
                if len(batch) >= BATCH_SIZE:
                    conn.executemany(insert_sql, batch)
                    loaded += len(batch)
                    batch = []
            if batch:
                conn.executemany(insert_sql, batch)
                loaded += len(batch)
        if loaded == 0:
            raise InputDataError(f"{spec.file_name} has a header but no data rows")

        conn.execute(
            "CREATE TABLE IF NOT EXISTS etl_raw_audit (table_name TEXT PRIMARY KEY, "
            "source_file TEXT, file_sha256 TEXT, rows_loaded INTEGER, loaded_at TEXT)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO etl_raw_audit VALUES (?,?,?,?,?)",
            (spec.table, spec.file_name, _sha256(path), loaded,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return loaded


def load_all(conn, raw_dir, headers):
    raw_dir = Path(raw_dir)
    counts = {}
    for spec in SOURCES:
        counts[spec.table] = _load_one(conn, spec, raw_dir / spec.file_name,
                                       headers[spec.table])
        log.info("loaded %-34s %9d rows", spec.table, counts[spec.table])
    return counts
