"""Run every sql/analysis/*.sql file and save the result as CSV (Part C).

Pure SQL in, CSV out: no pandas involved in producing the answers.
"""
import csv
import logging
from pathlib import Path

from .config import OUTPUT_DIR, SQL_DIR

log = logging.getLogger("pipeline.queries")


def run_all(conn, out_dir=None):
    out_dir = Path(out_dir or OUTPUT_DIR) / "query_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for path in sorted((SQL_DIR / "analysis").glob("*.sql")):
        cur = conn.execute(path.read_text(encoding="utf-8"))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        target = out_dir / f"{path.stem}.csv"
        with open(target, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(cols)
            writer.writerows([tuple(r) for r in rows])
        written[path.stem] = len(rows)
        log.info("query %-34s -> %5d rows -> %s", path.stem, len(rows), target.name)
    return written
