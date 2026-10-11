"""Part B: SQL data-quality framework.

Every check lives in its own file in sql/dq/ and looks like this:

    -- check: dq01_...            (id)
    -- description: ...           (what the rule is)
    -- handling: dropped|fixed|flagged ...
    -- why: ...                   (why we handled it that way)
    -- max_fail_pct: 1.0          (alarm threshold, % of total_rows)
    -- @found
    SELECT <bad_rows>, <total_rows>;       -- measured on the RAW tables
    -- @residual
    SELECT <bad_rows>;                     -- re-measured on staging/marts AFTER handling

A check PASSES when
  1. found_pct <= max_fail_pct   (upstream data is not catastrophically broken), and
  2. residual == 0               (our cleaning really removed / flagged the problem).
Any failing check raises DataQualityError -> the pipeline stops (the alarm).
"""
import logging
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from .errors import DataQualityError

log = logging.getLogger("pipeline.quality")

_META = re.compile(r"^--\s*(\w+):\s*(.*)$")


@dataclass
class DQCheck:
    check_id: str
    description: str
    handling: str
    why: str
    max_fail_pct: float
    found_sql: str
    residual_sql: str | None


@dataclass
class DQResult:
    check_id: str
    description: str
    handling: str
    why: str
    found_rows: int
    total_rows: int
    found_pct: float
    residual_rows: int | None
    max_fail_pct: float
    passed: bool
    reason: str


def parse_check(path):
    text = Path(path).read_text(encoding="utf-8")
    # Everything before the first '-- @found' marker is the metadata header.
    head, _, body = text.partition("-- @found")
    meta = {}
    for line in head.splitlines():
        m = _META.match(line.strip())
        if m:
            meta[m.group(1)] = m.group(2).strip()
    body = "-- @found" + body
    parts = re.split(r"^--\s*@(found|residual)\s*$", body, flags=re.MULTILINE)
    # parts = ['', 'found', sql, 'residual', sql]
    sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    for key in ("check", "description", "handling", "why", "max_fail_pct"):
        if key not in meta:
            raise ValueError(f"{path}: missing '-- {key}:' header")
    if "found" not in sections:
        raise ValueError(f"{path}: missing '-- @found' section")
    return DQCheck(
        check_id=meta["check"], description=meta["description"],
        handling=meta["handling"], why=meta["why"],
        max_fail_pct=float(meta["max_fail_pct"]),
        found_sql=sections["found"], residual_sql=sections.get("residual"),
    )


def load_checks(dq_dir):
    checks = [parse_check(p) for p in sorted(Path(dq_dir).glob("dq*.sql"))]
    if len(checks) < 5:
        raise ValueError(f"expected at least 5 DQ checks in {dq_dir}, found {len(checks)}")
    return checks


def run_checks(conn, checks):
    results = []
    for chk in checks:
        row = conn.execute(chk.found_sql).fetchone()
        found, total = int(row["bad_rows"] or 0), int(row["total_rows"] or 0)
        pct = round(100.0 * found / total, 3) if total else 0.0
        residual = None
        if chk.residual_sql:
            residual = int(conn.execute(chk.residual_sql).fetchone()["bad_rows"] or 0)

        reasons = []
        if pct > chk.max_fail_pct:
            reasons.append(f"{pct}% of rows fail, above the {chk.max_fail_pct}% tolerance")
        if residual:
            reasons.append(f"{residual} bad rows still present after handling")
        res = DQResult(chk.check_id, chk.description, chk.handling, chk.why, found,
                       total, pct, residual, chk.max_fail_pct, not reasons,
                       "; ".join(reasons) or "ok")
        results.append(res)
        log.log(logging.INFO if res.passed else logging.ERROR,
                "%-44s failing=%-6d of %-7d (%6.3f%%) residual=%s -> %s",
                chk.check_id, found, total, pct, residual,
                "PASS" if res.passed else "FAIL: " + res.reason)
    return results


def assert_all_passed(results):
    failed = [r for r in results if not r.passed]
    if failed:
        lines = [f"  {r.check_id}: {r.reason}" for r in failed]
        raise DataQualityError(
            f"DATA QUALITY ALARM - {len(failed)} of {len(results)} checks failed:\n"
            + "\n".join(lines) + "\nStaging/mart changes were rolled back; "
            "previously published tables are untouched.",
            results,
        )


def save_results(conn, run_id, results):
    """Persist the latest check results (used by the report). Replaces old rows."""
    conn.execute("DROP TABLE IF EXISTS dq_results")
    conn.execute(
        "CREATE TABLE dq_results (run_id TEXT, checked_at TEXT, check_id TEXT, "
        "description TEXT, handling TEXT, why TEXT, found_rows INTEGER, "
        "total_rows INTEGER, found_pct REAL, residual_rows INTEGER, "
        "max_fail_pct REAL, passed INTEGER, reason TEXT)"
    )
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.executemany(
        "INSERT INTO dq_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(run_id, now, r.check_id, r.description, r.handling, r.why, r.found_rows,
          r.total_rows, r.found_pct, r.residual_rows, r.max_fail_pct,
          int(r.passed), r.reason) for r in results],
    )
