"""Small SQLite helpers: connection, explicit transactions, SQL-file runner."""
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger("pipeline.db")


def connect(db_path):
    """Open the database in manual-transaction mode (isolation_level=None).

    We issue BEGIN/COMMIT ourselves because SQLite supports *transactional DDL*:
    a failed data-quality gate can ROLLBACK a rebuild of the staging + mart tables
    and the previous good versions are still there afterwards.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction(conn):
    conn.execute("BEGIN")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def split_sql(text):
    """Split a script into single statements (sqlite3.complete_statement aware).

    executescript() would silently COMMIT our open transaction, so we feed the
    statements one by one instead.
    """
    statements, buf = [], ""
    for line in text.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                statements.append(buf.strip())
            buf = ""
    if buf.strip() and any(not l.strip().startswith("--") for l in buf.splitlines() if l.strip()):
        statements.append(buf.strip())
    return statements


def run_sql_file(conn, path):
    path = Path(path)
    for stmt in split_sql(path.read_text(encoding="utf-8")):
        conn.execute(stmt)
    log.info("executed %s", path.name)


def run_sql_dir(conn, directory):
    """Run every .sql file in a folder in filename order (01_..., 02_...)."""
    for path in sorted(Path(directory).glob("*.sql")):
        run_sql_file(conn, path)


def table_counts(conn, prefixes=("stg_", "mart_")):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    out = {}
    for (name,) in rows:
        if name.startswith(prefixes):
            out[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    return out
