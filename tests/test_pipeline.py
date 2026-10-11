"""End-to-end tests. Expected values are recomputed independently with pandas straight
from the raw CSVs, so they check the SQL rather than repeat it."""
import hashlib
import shutil
import sqlite3

import pandas as pd
import pytest

from pipeline import run as run_mod
from pipeline.errors import DataQualityError, InputDataError
from pipeline.run import run_pipeline


def _db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _fingerprint(conn):
    """Row counts + a content hash of every data table (not the run log)."""
    out = {}
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'etl_run%' "
        "AND name != 'dq_results' ORDER BY name")]
    for n in names:
        rows = sorted((tuple(r) for r in conn.execute(f'SELECT * FROM "{n}"')), key=repr)
        h = hashlib.sha256(repr(rows).encode()).hexdigest()
        if n == "etl_raw_audit":      # timestamps differ between runs by design
            h = len(rows)
        out[n] = (len(rows), h)
    return out


@pytest.fixture()
def built(synthetic_dir, tmp_path):
    db = tmp_path / "t.db"
    run_pipeline(synthetic_dir, db, tmp_path / "out")
    return db, tmp_path / "out"


# ---------- Part A ---------------------------------------------------------
def test_idempotent_two_runs_identical(synthetic_dir, tmp_path):
    db = tmp_path / "t.db"
    run_pipeline(synthetic_dir, db, tmp_path / "out")
    conn = _db(db); first = _fingerprint(conn); conn.close()
    run_pipeline(synthetic_dir, db, tmp_path / "out")
    conn = _db(db); second = _fingerprint(conn); conn.close()
    assert first == second


def test_mart_grain_is_one_row_per_order(built):
    conn = _db(built[0])
    n, d = conn.execute("SELECT COUNT(*), COUNT(DISTINCT order_id) FROM mart_orders").fetchone()
    assert n == d > 0


def test_no_double_counting_of_items_revenue(built, synthetic_dir):
    conn = _db(built[0])
    mart_total = conn.execute("SELECT SUM(items_value) FROM mart_orders").fetchone()[0]
    items_total = conn.execute("SELECT SUM(price) FROM stg_order_items").fetchone()[0]
    assert mart_total == pytest.approx(items_total)
    # independent check from raw CSVs: valid items of orders that survive cleaning
    items = pd.read_csv(synthetic_dir / "olist_order_items_dataset.csv")
    orders = pd.read_csv(synthetic_dir / "olist_orders_dataset.csv").dropna(subset=["order_id"])
    custs = pd.read_csv(synthetic_dir / "olist_customers_dataset.csv")
    ok_orders = set(orders[orders.customer_id.isin(custs.customer_id)].order_id)
    items = items[items.order_id.isin(ok_orders) & (items.price > 0) & items.freight_value.notna()]
    assert mart_total == pytest.approx(items.price.sum())


def test_missing_file_fails_loudly(fresh_copy, tmp_path):
    (fresh_copy / "olist_order_items_dataset.csv").unlink()
    with pytest.raises(InputDataError, match="MISSING FILE.*olist_order_items_dataset.csv"):
        run_pipeline(fresh_copy, tmp_path / "t.db", tmp_path / "out")
    assert not (tmp_path / "t.db").exists()   # DB untouched when inputs are bad


def test_missing_column_fails_loudly(fresh_copy, tmp_path):
    p = fresh_copy / "olist_orders_dataset.csv"
    df = pd.read_csv(p).drop(columns=["order_estimated_delivery_date"])
    df.to_csv(p, index=False)
    with pytest.raises(InputDataError, match="MISSING COLUMN.*order_estimated_delivery_date"):
        run_pipeline(fresh_copy, tmp_path / "t.db", tmp_path / "out")


def test_cli_returns_exit_code_2_on_bad_input(fresh_copy, tmp_path):
    (fresh_copy / "olist_sellers_dataset.csv").unlink()
    code = run_mod.main(["--raw-dir", str(fresh_copy), "--db", str(tmp_path / "t.db"),
                         "--output-dir", str(tmp_path / "o")])
    assert code == 2


# ---------- Part B ---------------------------------------------------------
def test_dq_counts_match_injected_dirt(built):
    conn = _db(built[0])
    res = {r["check_id"]: r for r in conn.execute("SELECT * FROM dq_results")}
    assert len(res) >= 5
    assert all(r["passed"] == 1 for r in res.values())
    assert res["dq06_review_score_out_of_range"]["found_rows"] == 3
    assert res["dq01_orders_null_or_duplicate_id"]["found_rows"] >= 2 + 3   # blanks + dups
    assert res["dq08_orphan_child_rows"]["found_rows"] == 5 + 3 + 2


def test_dq_alarm_stops_pipeline_and_keeps_previous_marts(built, synthetic_dir, tmp_path):
    db, out = built
    conn = _db(db); before = _fingerprint(conn); conn.close()

    broken = tmp_path / "broken"
    shutil.copytree(synthetic_dir, broken)
    p = broken / "olist_orders_dataset.csv"
    df = pd.read_csv(p)
    df.loc[df.sample(frac=0.2, random_state=1).index, "order_id"] = ""   # 20% blank ids
    df.to_csv(p, index=False)

    with pytest.raises(DataQualityError, match="dq01_orders_null_or_duplicate_id"):
        run_pipeline(broken, db, out)

    conn = _db(db)
    after = _fingerprint(conn)
    # staging/mart tables are exactly as before (rolled back)
    for t in [k for k in before if k.startswith(("stg_", "mart_"))]:
        assert before[t] == after[t], t
    failed = conn.execute("SELECT COUNT(*) FROM dq_results WHERE passed = 0").fetchone()[0]
    assert failed >= 1
    assert conn.execute("SELECT status FROM etl_run_log ORDER BY started_at DESC, rowid DESC LIMIT 1"
                        ).fetchone()[0] == "FAILED"


def test_cli_returns_exit_code_3_on_dq_alarm(synthetic_dir, tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(synthetic_dir, broken)
    p = broken / "olist_order_reviews_dataset.csv"
    df = pd.read_csv(p)
    df["review_score"] = 9                                  # every score invalid
    df.to_csv(p, index=False)
    assert run_mod.main(["--raw-dir", str(broken), "--db", str(tmp_path / "t.db"),
                         "--output-dir", str(tmp_path / "o")]) == 3


# ---------- Part C ---------------------------------------------------------
def _q(db, name):
    from pipeline.config import SQL_DIR
    conn = _db(db)
    return pd.read_sql_query((SQL_DIR / "analysis" / f"{name}.sql").read_text(), conn)


def test_q1_matches_pandas_and_fills_calendar_gap(built):
    q1 = _q(built[0], "q1_mom_revenue_growth")
    months = pd.period_range(q1.month.iloc[0], q1.month.iloc[-1], freq="M").astype(str)
    assert list(q1.month) == list(months)                     # no skipped calendar month
    conn = _db(built[0])
    expected = conn.execute(
        "SELECT ROUND(SUM(items_value),2) FROM mart_orders WHERE is_valid_order=1").fetchone()[0]
    assert q1.revenue.sum() == pytest.approx(expected, abs=0.05)
    row = q1.iloc[5]
    if row.prev_month_revenue:
        assert row.mom_growth_pct == pytest.approx(
            100 * (row.revenue - row.prev_month_revenue) / row.prev_month_revenue, abs=0.1)


def test_q2_at_most_three_ranks_per_state(built):
    q2 = _q(built[0], "q2_top3_categories_per_state")
    assert q2.rank_in_state.max() <= 3
    assert q2.groupby("customer_state").rank_in_state.min().eq(1).all()


def test_q3_rolling_average_matches_pandas(built):
    q3 = _q(built[0], "q3_rolling_7day_orders")
    days = pd.to_datetime(q3.order_date)
    assert (days.diff().dropna() == pd.Timedelta(days=1)).all()   # continuous calendar
    expected = q3.orders.rolling(7).mean().round(2)
    pd.testing.assert_series_equal(q3.rolling_7d_avg, expected, check_names=False)


def test_q4_repeat_rate_uses_unique_id(built, synthetic_dir):
    q4 = _q(built[0], "q4_repeat_purchase_rate").set_index("identifier")
    assert q4.loc["customer_id (naive, wrong)", "repeat_customers"] == 0
    # independent: valid orders per customer_unique_id
    conn = _db(built[0])
    m = pd.read_sql_query(
        "SELECT order_id, customer_unique_id FROM mart_orders WHERE is_valid_order=1", conn)
    per = m.groupby("customer_unique_id").order_id.nunique()
    got = q4.loc["customer_unique_id (correct)"]
    assert got.customers == len(per)
    assert got.repeat_customers == (per >= 2).sum()
    assert got.repeat_customers > 0


def test_q5_delay_hurts_reviews(built):
    b = _q(built[0], "q5b_review_by_delay_bucket")
    assert b.avg_review_score.iloc[-1] < b.avg_review_score.iloc[0]
    q5 = _q(built[0], "q5_delivery_delay_vs_review")
    assert q5.review_score.iloc[-1] == "ALL"
    one, five = q5[q5.review_score == "1"].iloc[0], q5[q5.review_score == "5"].iloc[0]
    assert one.avg_delay_days > five.avg_delay_days
