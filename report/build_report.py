"""Build the PDF report (max 5 pages) from the database and the saved query results.

    python -m report.build_report --db db/olist.db --out outputs/report.pdf

Every number in the report is read from the database / query CSVs at build time, so
the report always matches the data that was loaded. The memo text is a DRAFT built
from those numbers: read it, check it against the charts, and rewrite it in your own
words before you submit (see docs/VIVA_NOTES.md).
"""
import argparse
import sqlite3
import statistics
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm, inch  # noqa: E402
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate,  # noqa: E402
                                Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
MAX_PAGES = 5

# Palette: first two slots of a validated categorical set + neutral ink.
BLUE, ORANGE, GRAY, INK, GRID = "#2a78d6", "#eb6834", "#8a8985", "#2b2b2a", "#e3e2de"

DELIVERED_REVIEWED = ("order_status = 'delivered' AND delay_days IS NOT NULL "
                      "AND review_score IS NOT NULL")


# --------------------------------------------------------------------------- data
def load(db_path, qdir):
    conn = sqlite3.connect(db_path)
    d = {
        "dq": pd.read_sql_query("SELECT * FROM dq_results ORDER BY check_id", conn),
        "weekly": pd.read_sql_query("SELECT * FROM mart_weekly_metrics ORDER BY week_start", conn),
        "audit": pd.read_sql_query("SELECT table_name, rows_loaded FROM etl_raw_audit", conn),
        "source": conn.execute(
            "SELECT data_source FROM etl_run_log ORDER BY finished_at DESC LIMIT 1").fetchone()[0],
        "q": {p.stem: pd.read_csv(p) for p in Path(qdir).glob("*.csv")},
    }
    d["delivered"] = pd.read_sql_query(
        f"SELECT customer_state, review_score, delay_days, dispatch_days, transit_days "
        f"FROM mart_orders WHERE {DELIVERED_REVIEWED}", conn)
    d["counts"] = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                   for t in ("stg_orders", "mart_orders", "mart_order_items", "mart_weekly_metrics")}
    conn.close()
    return d


# ------------------------------------------------------------------------- charts
def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK, labelsize=6.5, length=2)
    ax.grid(axis="y", color=GRID, lw=0.5)
    ax.set_axisbelow(True)


def make_charts(d, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 7, "axes.titlesize": 8, "axes.titleweight": "bold",
                         "axes.labelsize": 7, "text.color": INK, "axes.labelcolor": INK})
    paths = {}

    # 1. monthly revenue + MoM growth (two stacked panels, one axis each)
    q1 = d["q"]["q1_mom_revenue_growth"]
    fig, (a, b) = plt.subplots(2, 1, figsize=(3.55, 2.7), sharex=True,
                               gridspec_kw={"height_ratios": [2, 1.1], "hspace": 0.12})
    x = range(len(q1))
    a.bar(x, q1.revenue / 1000, color=BLUE, width=0.7)
    a.set_ylabel("Revenue (BRL thousand)")
    a.set_title("Chart 1 - Monthly revenue and month-over-month growth", loc="left")
    g = q1.mom_growth_pct.fillna(0).clip(-100, 100)
    b.bar(x, g, color=[ORANGE if v < 0 else BLUE for v in g], width=0.7)
    b.axhline(0, color=INK, lw=0.6)
    b.set_ylabel("MoM growth (%)\n(capped at +/-100)")
    ticks = list(range(0, len(q1), 3))
    b.set_xticks(ticks)
    b.set_xticklabels([q1.month[i] for i in ticks], rotation=45, ha="right")
    _style(a); _style(b)
    fig.savefig(out_dir / "c1_revenue.png", dpi=220, bbox_inches="tight")
    plt.close(fig); paths["c1"] = out_dir / "c1_revenue.png"

    # 2. average review score by delay bucket
    q5b = d["q"]["q5b_review_by_delay_bucket"]
    labels = [s.split(": ", 1)[1].replace(" days", " d") for s in q5b.delay_bucket]
    fig, ax = plt.subplots(figsize=(3.55, 2.7))
    cols = [BLUE if "late" not in l else ORANGE for l in labels]
    bars = ax.bar(range(len(q5b)), q5b.avg_review_score, color=cols, width=0.65)
    for rect, v, n in zip(bars, q5b.avg_review_score, q5b.orders):
        ax.text(rect.get_x() + rect.get_width() / 2, v + 0.04, f"{v:.2f}\nn={n:,}",
                ha="center", va="bottom", fontsize=5.8)
    ax.set_ylim(0, 5.6)
    ax.set_xticks(range(len(q5b)))
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel("Average review score (stars)")
    ax.set_title("Chart 2 - Review score by delivery vs promised date", loc="left")
    _style(ax)
    fig.savefig(out_dir / "c2_bucket.png", dpi=220, bbox_inches="tight")
    plt.close(fig); paths["c2"] = out_dir / "c2_bucket.png"

    # 3. review score mix: on time vs late
    df = d["delivered"]
    mix = (df.assign(late=df.delay_days > 0).groupby("late").review_score
           .value_counts(normalize=True).mul(100).unstack(fill_value=0))
    fig, ax = plt.subplots(figsize=(3.55, 2.7))
    w = 0.38
    xs = list(range(1, 6))
    for off, flag, col, name in ((-w / 2, False, BLUE, "On time or early"), (w / 2, True, ORANGE, "Late")):
        vals = [mix.loc[flag].get(s, 0) if flag in mix.index else 0 for s in xs]
        ax.bar([s + off for s in xs], vals, width=w, color=col, label=name)
    ax.set_xlabel("Review score (stars)")
    ax.set_ylabel("Share of orders in group (%)")
    ax.set_title("Chart 3 - Review score mix: late vs on-time orders", loc="left")
    ax.legend(frameon=False, fontsize=6.5, loc="upper center")
    _style(ax)
    fig.savefig(out_dir / "c3_mix.png", dpi=220, bbox_inches="tight")
    plt.close(fig); paths["c3"] = out_dir / "c3_mix.png"

    # 4. weekly north star + on-time rate (two panels, trimmed edges)
    wk = trimmed_weeks(d["weekly"])
    fig, (a, b) = plt.subplots(2, 1, figsize=(3.55, 2.7), sharex=True,
                               gridspec_kw={"height_ratios": [1.3, 1], "hspace": 0.12})
    xs = pd.to_datetime(wk.week_start)
    a.plot(xs, wk.satisfied_orders, color=BLUE, lw=1.4)
    a.set_ylabel("Satisfied orders\n(north star)")
    a.set_title("Chart 4 - Weekly north star and on-time rate", loc="left")
    b.plot(xs, wk.on_time_rate_pct, color=ORANGE, lw=1.4)
    b.set_ylabel("On-time rate (%)")
    b.set_ylim(max(0, wk.on_time_rate_pct.min() - 5), 100)
    b.tick_params(axis="x", rotation=30)
    _style(a); _style(b)
    fig.savefig(out_dir / "c4_weekly.png", dpi=220, bbox_inches="tight")
    plt.close(fig); paths["c4"] = out_dir / "c4_weekly.png"
    return paths


def trimmed_weeks(weekly, min_orders=30):
    """Drop tiny edge weeks and the newest (still incomplete) week."""
    wk = weekly[weekly.valid_orders >= min_orders].copy()
    return wk.iloc[:-1] if len(wk) > 2 else wk


# --------------------------------------------------------------------- memo maths
def memo_numbers(d):
    df = d["delivered"]
    late = df[df.delay_days > 0]
    ok = df[df.delay_days <= 0]
    low_all = (df.review_score <= 2).sum()
    q5b = d["q"]["q5b_review_by_delay_bucket"].set_index("delay_bucket")
    x1 = d["q"]["x1_late_delivery_by_state"]
    worst = x1.head(3)
    worst_states = list(worst.customer_state)
    in_worst = late[late.customer_state.isin(worst_states)]
    n = {
        "n_reviewed": len(df),
        "late_share": 100 * len(late) / len(df),
        "late_avg": late.review_score.mean(), "ok_avg": ok.review_score.mean(),
        "late_low": 100 * (late.review_score <= 2).mean(),
        "ok_low": 100 * (ok.review_score <= 2).mean(),
        "late_low_share": 100 * (late.review_score <= 2).sum() / low_all,
        "b4": q5b.avg_review_score.iloc[3], "b5": q5b.avg_review_score.iloc[4],
        "b6": q5b.avg_review_score.iloc[5],
        "worst_states": worst_states,
        "worst_rates": (worst.late_rate_pct.min(), worst.late_rate_pct.max()),
        "avg_rate": 100 * len(late) / len(df),
        "disp_excess": late.dispatch_days.mean() - ok.dispatch_days.mean(),
        "trans_excess": late.transit_days.mean() - ok.transit_days.mean(),
        "buffer_days": int(-(-statistics.median(in_worst.delay_days) // 1)) if len(in_worst) else 3,
    }
    n["gap"] = n["ok_avg"] - n["late_avg"]
    n["uplift"] = 0.5 * (n["late_share"] / 100) * n["gap"]
    # halve the late orders -> they take on the on-time low-review rate
    removed = 0.5 * len(late) * ((n["late_low"] - n["ok_low"]) / 100)
    n["low_removed_pct"] = 100 * removed / low_all
    n["flat_early"] = (q5b.avg_review_score.iloc[:3].max() - q5b.avg_review_score.iloc[:3].min()) <= 0.15
    n["transit_driven"] = n["trans_excess"] >= n["disp_excess"]
    return n


# ----------------------------------------------------------------------- layout
def styles():
    ss = getSampleStyleSheet()
    s = {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontSize=15, spaceAfter=4, textColor=INK),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=10.5, spaceBefore=6, spaceAfter=3, textColor=INK),
        "body": ParagraphStyle("body", parent=ss["BodyText"], fontSize=8, leading=10.2, alignment=TA_LEFT),
        "small": ParagraphStyle("small", parent=ss["BodyText"], fontSize=6.8, leading=8.4),
        "cell": ParagraphStyle("cell", parent=ss["BodyText"], fontSize=6.6, leading=8),
        "cellb": ParagraphStyle("cellb", parent=ss["BodyText"], fontSize=6.6, leading=8, fontName="Helvetica-Bold"),
        "memo": ParagraphStyle("memo", parent=ss["BodyText"], fontSize=9, leading=12.2),
        "banner": ParagraphStyle("banner", parent=ss["BodyText"], fontSize=7.5, leading=9.5,
                                 textColor=colors.HexColor("#8a2a0a"), backColor=colors.HexColor("#fdebe3"),
                                 borderPadding=4),
    }
    return s


def P(text, style):
    return Paragraph(text, style)


def table(rows, widths, st, header=True, font=6.6, zebra=True):
    cell, cellb = st["cell"], st["cellb"]
    data = [[c if not isinstance(c, str) else P(c, cellb if (header and i == 0) else cell)
             for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor(GRID)),
             ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
             ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efeeea")))
    t.setStyle(TableStyle(style))
    return t


def fmt_money(v):
    return f"{v:,.0f}"


def page1(d, st, W):
    out = [P("Weekly Business Review - Olist Marketplace", st["h1"]),
           P(f"Take-home assignment 1 | built {date.today():%d %b %Y} | data: {d['source']}", st["small"])]
    if "SYNTHETIC" in d["source"]:
        out += [Spacer(1, 3), P("<b>DEMO BUILD.</b> Generated from SYNTHETIC data "
                                "(tools/make_synthetic_data.py). The numbers below are not real Olist "
                                "results. Re-run the pipeline on the Kaggle CSVs before submitting.", st["banner"])]
    c = d["counts"]
    out += [P("1. Pipeline and data-quality findings", st["h2"]),
            P("<b>Pipeline.</b> Nine CSVs are validated (files and columns), loaded as untouched <i>raw_*</i> "
              "tables, cleaned into <i>stg_*</i> tables and combined into marts: <i>mart_orders</i> (one row per "
              f"order, {c['mart_orders']:,} rows), <i>mart_order_items</i> ({c['mart_order_items']:,}) and "
              f"<i>mart_weekly_metrics</i> ({c['mart_weekly_metrics']:,} weeks). Raw tables are rebuilt atomically "
              "and staging/marts are rebuilt together with the checks in one transaction, so a second run "
              "reproduces identical tables (verified by a test), and a failed check rolls the rebuild back "
              "and stops the pipeline with exit code 3.", st["body"]),
            Spacer(1, 4),
            P("Nine SQL checks ran on the raw data; <b>rows failing</b> is measured before cleaning, "
              "'after' is re-measured on staging/marts. Duplicates count the surplus rows.", st["body"]),
            Spacer(1, 3)]
    rows = [["Check (sql/dq/)", "Rule", "Rows failing", "After", "Handling", "Why this handling"]]
    for _, r in d["dq"].iterrows():
        rows.append([r.check_id.split("_", 1)[0].upper() + " " + r.check_id.split("_", 1)[1].replace("_", " "),
                     r.description,
                     f"{r.found_rows:,} of {r.total_rows:,} ({r.found_pct:.2f}%)",
                     "0" if r.residual_rows in (0, None) else str(int(r.residual_rows)),
                     r.handling, r.why])
    out.append(table(rows, [2.3 * cm, 3.4 * cm, 2.2 * cm, 0.9 * cm, 3.0 * cm, W - 11.8 * cm], st))
    out.append(Spacer(1, 3))
    out.append(P("Checks DQ05-DQ09 are of my own design. Alarm rule: a check fails if more than its "
                 "tolerance (max_fail_pct in the SQL header) of rows are bad, or if any bad row survives the "
                 "handling.", st["small"]))
    return out


def page2(d, st, W):
    q = d["q"]
    out = [P("2. SQL query results (Part C - full outputs in outputs/query_results/*.csv)", st["h2"])]

    # Q1
    q1 = q["q1_mom_revenue_growth"]
    out.append(P("<b>Q1 Month-over-month revenue.</b> Revenue = item price of valid orders (not canceled/"
                 "unavailable), by purchase month. A calendar table keeps empty months as 0, so growth is "
                 "never computed against the wrong month.", st["body"]))
    half = (len(q1) + 1) // 2

    def q1rows(sub):
        r = [["Month", "Revenue (BRL)", "MoM %"]]
        for _, x in sub.iterrows():
            r.append([x.month, fmt_money(x.revenue),
                      "-" if pd.isna(x.mom_growth_pct) else f"{x.mom_growth_pct:+.1f}"])
        return r
    t1 = table(q1rows(q1.iloc[:half]), [1.6 * cm, 2.6 * cm, 1.6 * cm], st)
    t2 = table(q1rows(q1.iloc[half:]), [1.6 * cm, 2.6 * cm, 1.6 * cm], st)
    out.append(Table([[t1, t2]], colWidths=[W / 2, W / 2], style=[("VALIGN", (0, 0), (-1, -1), "TOP")]))

    # Q2
    q2 = q["q2_top3_categories_per_state"]
    top_states = (q2.groupby("customer_state").revenue.sum().sort_values(ascending=False).head(6).index)
    r = [["State", "#1 category (BRL)", "#2 category (BRL)", "#3 category (BRL)"]]
    for s in top_states:
        sub = q2[q2.customer_state == s].sort_values(["rank_in_state", "category"]).head(3)
        cells = [f"{x.category} ({fmt_money(x.revenue)})" for _, x in sub.iterrows()]
        r.append([s] + cells + [""] * (3 - len(cells)))
    out += [Spacer(1, 4),
            P(f"<b>Q2 Top 3 categories per customer state</b> (DENSE_RANK; shown for the 6 largest states of "
              f"{q2.customer_state.nunique()}).", st["body"]),
            table(r, [1.3 * cm, (W - 1.3 * cm) / 3, (W - 1.3 * cm) / 3, (W - 1.3 * cm) / 3], st)]

    # Q3
    q3 = q["q3_rolling_7day_orders"].dropna(subset=["rolling_7d_avg"])
    peak = q3.loc[q3.rolling_7d_avg.idxmax()]
    last = q3.iloc[-1]
    out += [Spacer(1, 4),
            P(f"<b>Q3 7-day rolling average of daily orders</b> (continuous calendar, zero-order days "
              f"included, first 6 days left blank). Highest 7-day average: <b>{peak.rolling_7d_avg:.1f}</b> "
              f"orders/day, window ending {peak.order_date}. Latest: <b>{last.rolling_7d_avg:.1f}</b> "
              f"(window ending {last.order_date}).", st["body"])]

    # Q4
    q4 = q["q4_repeat_purchase_rate"]
    r = [["Identifier used", "Customers", "Repeat customers", "Repeat rate", "Avg orders / customer"]]
    for _, x in q4.iterrows():
        r.append([x.identifier, f"{x.customers:,}", f"{x.repeat_customers:,}", f"{x.repeat_rate_pct:.2f}%",
                  f"{x.avg_orders_per_customer:.3f}"])
    out += [Spacer(1, 4),
            P("<b>Q4 Repeat-purchase rate.</b> customer_id is regenerated for every order, so it can never "
              "show a repeat; the real person is customer_unique_id.", st["body"]),
            table(r, [5.0 * cm, 2.2 * cm, 3.0 * cm, 2.2 * cm, W - 12.4 * cm], st)]

    # Q5
    q5, q5b = q["q5_delivery_delay_vs_review"], q["q5b_review_by_delay_bucket"]
    r5 = [["Review score", "Orders", "Avg delay (d)", "% late", "Avg delivery (d)"]]
    for _, x in q5.iterrows():
        r5.append([str(x.review_score), f"{x.orders:,}", f"{x.avg_delay_days:+.2f}", f"{x.pct_late:.1f}",
                   f"{x.avg_delivery_days:.1f}"])
    r5b = [["Delivered vs promised", "Orders", "Avg score", "% 1-2 stars"]]
    for _, x in q5b.iterrows():
        r5b.append([x.delay_bucket.split(": ", 1)[1], f"{x.orders:,}", f"{x.avg_review_score:.2f}",
                    f"{x.pct_low_reviews_1_2:.1f}"])
    out += [Spacer(1, 4),
            P("<b>Q5 Delivery delay vs estimate, and review score.</b> Delay = delivery date minus estimated "
              "date in whole days (positive = late), delivered orders with a review. Left: by review score. "
              "Right: by delay bucket.", st["body"]),
            Table([[table(r5, [1.9 * cm, 1.6 * cm, 2.0 * cm, 1.3 * cm, 2.3 * cm], st),
                    table(r5b, [3.3 * cm, 1.5 * cm, 1.6 * cm, 1.9 * cm], st)]],
                  colWidths=[W * 0.5, W * 0.5], style=[("VALIGN", (0, 0), (-1, -1), "TOP")])]
    return out


METRICS = [
    ("NORTH STAR<br/>Satisfied orders per week",
     "COUNT of orders with status 'delivered' AND review_score &gt;= 4, grouped by purchase week.",
     "Counts orders where the customer both received the goods and was happy, so it rises only if volume AND "
     "satisfaction rise together; it cannot be gamed by cheap volume or by chasing ratings on a few orders."),
    ("Weekly GMV (supporting)",
     "SUM(item price) over orders with status not in (canceled, unavailable), by purchase week. Freight excluded.",
     "Scale check: the north star must not improve because the business shrank."),
    ("On-time delivery rate (guardrail)",
     "Delivered orders with delivery date &lt;= estimated date / delivered orders with a delivery date (compared "
     "as dates, not timestamps).",
     "The operational lever behind satisfaction; it moves before reviews do."),
    ("Low-review rate (guardrail)",
     "Delivered orders with review_score in (1, 2) / delivered orders with a review.",
     "The north star counts 4-5 stars only; this exposes the unhappy tail it hides."),
    ("Repeat-purchase rate (supporting)",
     "COUNT(customer_unique_id with 2+ valid orders) / COUNT(customer_unique_id with 1+ valid order).",
     "Retention: satisfied customers should come back. Uses customer_unique_id because customer_id is per order."),
]


def page3(d, st, W):
    wk = trimmed_weeks(d["weekly"]).tail(8)
    q4 = d["q"]["q4_repeat_purchase_rate"]
    rep = q4.iloc[0].repeat_rate_pct
    vals = [f"{wk.satisfied_orders.mean():.0f} per week", f"{fmt_money(wk.gmv.mean())} BRL per week",
            f"{wk.on_time_rate_pct.mean():.1f}%", f"{wk.low_review_rate_pct.mean():.1f}%", f"{rep:.2f}% (whole period)"]
    rows = [["Metric", "Exact formula", "Why it matters", "Recent value*"]]
    for (name, formula, why), v in zip(METRICS, vals):
        rows.append([name, formula, why, v])
    out = [P("3. Metric definitions (Part D)", st["h2"]),
           table(rows, [3.2 * cm, 5.6 * cm, 6.2 * cm, W - 15.0 * cm], st),
           Spacer(1, 3),
           P("*Mean of the last 8 complete weeks (tiny edge weeks and the newest, still-incomplete week are "
             "dropped). Weeks are Monday-start purchase weeks. Newer orders are not yet all delivered or "
             "reviewed, so the latest weeks are the least reliable.", st["small"]),
           Spacer(1, 6),
           P("Conventions used in every query: <b>valid order</b> = status not 'canceled' or 'unavailable'; "
             "<b>revenue</b> = item price (freight excluded); <b>late</b> = delivered after the estimated date "
             "(whole days); one review per order (latest answer); one row per order in the mart, with items, "
             "payments and reviews pre-aggregated before joining so nothing is double counted.", st["body"])]
    return out


def page4(d, st, W, charts):
    imgs = {k: Image(str(v), width=W / 2 - 4, height=(W / 2 - 4) * 2.7 / 3.55) for k, v in charts.items()}
    grid = Table([[imgs["c1"], imgs["c2"]], [imgs["c3"], imgs["c4"]]], colWidths=[W / 2, W / 2],
                 style=[("VALIGN", (0, 0), (-1, -1), "TOP")])
    return [P("4. Charts", st["h2"]), grid,
            Spacer(1, 4),
            P("Chart 1: monthly revenue (top) and its month-over-month change (bottom; empty months are 0, so "
              "growth after a gap is undefined). Chart 2: average review score by how the delivery date compared "
              "with the promised date. Chart 3: distribution of review scores for orders that arrived on time or "
              "early versus late. Chart 4: the north-star metric by purchase week, with the on-time rate beneath "
              "it (edge weeks trimmed).", st["small"])]


def memo(d, st, W):
    n = memo_numbers(d)
    ws = ", ".join(n["worst_states"])
    lo, hi = n["worst_rates"]
    if n["transit_driven"]:
        reco = (f"<b>Recommendation.</b> Run a four-week pilot of a <b>promise-date buffer</b> in the three "
                f"states with the highest late rate ({ws}; {lo:.0f}-{hi:.0f}% late vs {n['avg_rate']:.0f}% overall): "
                f"add <b>{n['buffer_days']} days</b> (the median overshoot of late orders there) to the delivery "
                f"estimate shown at checkout, with a control group on today's estimates. Success = low-review "
                f"rate (1-2 stars) in the pilot states falls without checkout conversion dropping by more "
                f"than an agreed threshold. Across all late orders the extra time is spent in carrier "
                f"transit (+{n['trans_excess']:.1f} days vs on-time orders) rather than in seller dispatch "
                f"(+{n['disp_excess']:.1f} days), which points to the promise and the carrier lane, not the seller.")
    else:
        reco = (f"<b>Recommendation.</b> Introduce a <b>seller dispatch SLA</b>: sellers whose orders reach the "
                f"carrier later than the SLA get a warning and then reduced search ranking. Pilot it first for "
                f"orders shipped to the states with the highest late rate ({ws}; {lo:.0f}-{hi:.0f}% late vs "
                f"{n['avg_rate']:.0f}% overall). Late orders lose more time before the carrier receives them "
                f"(+{n['disp_excess']:.1f} days vs on-time orders) than in transit (+{n['trans_excess']:.1f} "
                f"days). Success = late rate in the pilot states down, measured weekly.")
    story = [P("5. Memo to the Vice President", st["h2"]),
             P("<b>To:</b> Vice President, Marketplace &nbsp;&nbsp; <b>From:</b> Data Analyst &nbsp;&nbsp; "
               f"<b>Date:</b> {date.today():%d %b %Y}<br/><b>Re:</b> What is hurting customer satisfaction", st["memo"]),
             Spacer(1, 6)]
    if "SYNTHETIC" in d["source"]:
        story += [P("<b>DEMO:</b> written from synthetic data. Replace with a memo based on the real run.", st["banner"]),
                  Spacer(1, 6)]
    story += [
        P(f"<b>Key finding.</b> Late delivery is the clearest driver of bad reviews we can act on. Delivered "
          f"orders that arrive after the promised date score <b>{n['late_avg']:.2f} stars</b> on average, "
          f"against <b>{n['ok_avg']:.2f}</b> for on-time orders, and <b>{n['late_low']:.0f}%</b> of them get 1-2 "
          f"stars (<b>{n['ok_low']:.0f}%</b> for on-time). {n['late_share']:.0f}% of reviewed orders are late, "
          f"and they produce <b>{n['late_low_share']:.0f}%</b> of all 1-2 star reviews.", st["memo"]),
        Spacer(1, 7),
        P("<b>Evidence.</b>", st["memo"]),
        P(f"&bull; The penalty grows with lateness: {n['b4']:.2f} stars for 1-3 days late, {n['b5']:.2f} for 4-7 "
          f"days, {n['b6']:.2f} for 8+ days (Chart 2, Q5).", st["memo"]),
        P("&bull; Orders delivered early or on the promised date all score about the same, so the problem is "
          "missing the promise, not slow delivery as such (Chart 2)." if n["flat_early"] else
          "&bull; Orders delivered earlier than promised score differently from each other, so check Chart 2 "
          "before claiming that only missing the promise matters.", st["memo"]),
        P(f"&bull; Lateness is concentrated by region: {ws} have the highest late rates "
          f"({lo:.0f}-{hi:.0f}%) among states with 50+ orders (query x1).", st["memo"]),
        Spacer(1, 7),
        P(reco, st["memo"]),
        Spacer(1, 7),
        P(f"<b>Expected impact (rough).</b> If late orders were halved and behaved like on-time orders, "
          f"1-2 star reviews would fall by roughly <b>{n['low_removed_pct']:.0f}%</b> and the average score "
          f"would rise by about {n['uplift']:.2f} stars (0.5 x {n['late_share']:.0f}% late share x "
          f"{n['gap']:.2f}-star gap). This assumes the two groups differ only in lateness.", st["memo"]),
        Spacer(1, 7),
        P("<b>Caveat.</b> This is an association, not proof of cause: late orders may also differ in product "
          "type or seller. The pilot with a control group is how we confirm it before a national rollout.",
          st["memo"]),
    ]
    return story


def build(db_path, qdir, out_pdf, chart_dir):
    d = load(db_path, qdir)
    st = styles()
    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out_pdf), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.4 * cm, bottomMargin=1.3 * cm,
                            title="Weekly Business Review - Olist", author="Data Analyst")
    W = A4[0] - 3.0 * cm
    charts = make_charts(d, Path(chart_dir))
    story = (page1(d, st, W) + [PageBreak()] + page2(d, st, W) + [PageBreak()] +
             page3(d, st, W) + page4(d, st, W, charts) + [PageBreak()] + memo(d, st, W))
    doc.build(story)
    pages = len(PdfReader(str(out_pdf)).pages)
    if pages > MAX_PAGES:
        raise SystemExit(f"report is {pages} pages, limit is {MAX_PAGES}")
    return pages


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "db" / "olist.db"))
    ap.add_argument("--query-dir", default=str(ROOT / "outputs" / "query_results"))
    ap.add_argument("--out", default=str(ROOT / "outputs" / "report.pdf"))
    ap.add_argument("--chart-dir", default=str(ROOT / "outputs" / "charts"))
    a = ap.parse_args()
    print(f"wrote {a.out} ({build(a.db, a.query_dir, a.out, a.chart_dir)} pages)")
