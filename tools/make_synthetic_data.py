"""Generate a SYNTHETIC dataset with the same schema (and the same kinds of dirt)
as the Olist Brazilian E-Commerce dataset.

Why this exists: the real data needs a Kaggle login, so automated tests and smoke
runs use this instead. It is NOT real data and nothing in the report built from it
means anything about Olist. The generator writes SYNTHETIC_DATA.txt next to the CSVs
and the report prints a banner when it sees that file.

    python tools/make_synthetic_data.py --out data/synthetic --orders 20000

The data deliberately contains the quirks the pipeline must handle: one customer_id
per order, duplicate order rows, blank ids, delivery before purchase, orders with
unknown customers, delivered orders without a delivery date, several reviews per
order, invalid review scores, bad item prices, orphan child rows, payment totals that
differ from price + freight.
"""
import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

FMT = "%Y-%m-%d %H:%M:%S"

# state -> (population weight, typical transit days). Far-away states are slower.
STATES = {
    "SP": (0.42, 3), "RJ": (0.13, 7), "MG": (0.12, 6), "RS": (0.055, 8), "PR": (0.05, 7),
    "SC": (0.037, 8), "BA": (0.034, 11), "DF": (0.02, 8), "ES": (0.02, 8), "GO": (0.02, 8),
    "PE": (0.017, 12), "CE": (0.013, 13), "PA": (0.01, 15), "MT": (0.01, 12), "MA": (0.007, 14),
    "MS": (0.007, 10), "PB": (0.005, 13), "RN": (0.005, 13), "PI": (0.005, 14), "AL": (0.004, 14),
    "SE": (0.004, 13), "TO": (0.003, 12), "RO": (0.003, 15), "AM": (0.002, 20), "AC": (0.001, 20),
}
CATEGORIES = {  # portuguese -> english (two deliberately left untranslated, as in the real data)
    "cama_mesa_banho": "bed_bath_table", "beleza_saude": "health_beauty",
    "esporte_lazer": "sports_leisure", "informatica_acessorios": "computers_accessories",
    "moveis_decoracao": "furniture_decor", "utilidades_domesticas": "housewares",
    "relogios_presentes": "watches_gifts", "telefonia": "telephony", "automotivo": "auto",
    "brinquedos": "toys", "cool_stuff": "cool_stuff", "ferramentas_jardim": "garden_tools",
    "perfumaria": "perfumery", "bebes": "baby", "eletronicos": "electronics",
    "papelaria": "stationery", "pet_shop": "pet_shop", "consoles_games": "consoles_games",
    "eletrodomesticos": "home_appliances", "livros_interesse_geral": "books_general_interest",
    "alimentos": "food", "audio": "audio", "pc_gamer": None,
    "portateis_cozinha_e_preparadores_de_alimentos": None,
}
PAY_TYPES = [("credit_card", 0.74), ("boleto", 0.19), ("voucher", 0.04), ("debit_card", 0.03)]


def wchoice(rng, pairs):
    r, acc = rng.random(), 0.0
    for value, w in pairs:
        acc += w
        if r <= acc:
            return value
    return pairs[-1][0]


def hex_id(rng):
    return f"{rng.getrandbits(128):032x}"


def review_score(rng, delay_days):
    if delay_days is None or delay_days <= 0:
        w = [.03, .02, .07, .20, .68]
    elif delay_days <= 3:
        w = [.08, .06, .14, .28, .44]
    elif delay_days <= 7:
        w = [.25, .15, .20, .20, .20]
    else:
        w = [.55, .20, .12, .07, .06]
    return rng.choices([1, 2, 3, 4, 5], weights=w)[0]


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def generate(out_dir, n_orders=20000, seed=42):
    rng = random.Random(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    state_list = list(STATES)
    state_w = [STATES[s][0] for s in state_list]

    # --- sellers & products ------------------------------------------------
    sellers = []
    for _ in range(max(40, n_orders // 70)):
        st = rng.choices(state_list, weights=state_w)[0]
        sellers.append((hex_id(rng), f"{rng.randint(1000, 99990)}", f"city_{st}_{rng.randint(1, 5)}", st))
    cat_names = list(CATEGORIES)
    products = []
    for _ in range(max(120, n_orders // 25)):
        cat = rng.choice(cat_names) if rng.random() > 0.015 else ""
        products.append((hex_id(rng), cat, rng.randint(10, 60), rng.randint(100, 2000),
                         rng.randint(1, 6), rng.randint(100, 8000), rng.randint(10, 60),
                         rng.randint(5, 40), rng.randint(10, 50)))

    # --- order dates: growth trend + Black Friday spike + 2016 gap -----------
    start, end = datetime(2017, 1, 1), datetime(2018, 8, 29)
    n_days = (end - start).days
    day_w = []
    for i in range(n_days + 1):
        d = start + timedelta(days=i)
        w = 1 + 6.0 * i / n_days
        if d.date() == datetime(2017, 11, 24).date():
            w *= 5
        day_w.append(w)
    n_2016 = max(8, n_orders // 400)
    purchase_days = rng.choices(range(n_days + 1), weights=day_w, k=n_orders - n_2016)
    purchases = [start + timedelta(days=d, seconds=rng.randint(0, 86399)) for d in purchase_days]
    for _ in range(n_2016):  # Sep/Oct/Dec 2016 trickle, no November (like the real data)
        m = rng.choice([9, 10, 10, 12])
        purchases.append(datetime(2016, m, rng.randint(1, 28), rng.randint(0, 23), rng.randint(0, 59), 0))
    purchases.sort()

    customers, orders, items, payments, reviews = [], [], [], [], []
    unique_ids = []
    delivered_idx = []

    for n, purchase in enumerate(purchases):
        order_id, customer_id = hex_id(rng), hex_id(rng)
        if unique_ids and rng.random() < 0.033:
            unique_id = rng.choice(unique_ids)          # a returning person
        else:
            unique_id = hex_id(rng)
            unique_ids.append(unique_id)
        st = rng.choices(state_list, weights=state_w)[0]
        customers.append((customer_id, unique_id, f"{rng.randint(1000, 99990)}",
                          f"city_{st}_{rng.randint(1, 8)}", st))

        status = wchoice(rng, [("delivered", .965), ("shipped", .011), ("canceled", .006),
                               ("unavailable", .006), ("invoiced", .003), ("processing", .003),
                               ("created", .001), ("approved", .005)])
        transit_mean = STATES[st][1]
        est_total = int(8 + 1.5 * transit_mean + rng.randint(0, 6))
        p_late = 0.04 + 0.011 * (transit_mean - 3)
        if rng.random() < p_late:
            actual_total = est_total + int(rng.expovariate(1 / 6)) + 1
        else:
            actual_total = max(2, est_total - rng.randint(0, 12))
        dispatch = min(max(0.5, rng.gauss(2.5, 1.4)), actual_total - 1)
        if actual_total > est_total and rng.random() < 0.4:   # some lateness is seller-side
            dispatch = min(dispatch + rng.uniform(2, 7), actual_total - 1)

        approved = purchase + timedelta(hours=rng.randint(0, 20))
        carrier = purchase + timedelta(days=dispatch)
        delivered = purchase + timedelta(days=actual_total, hours=rng.randint(-6, 8))
        estimated = (purchase + timedelta(days=est_total)).replace(hour=0, minute=0, second=0)
        delay = (delivered.date() - estimated.date()).days

        f_approved = f_carrier = f_delivered = ""
        if status == "created":
            pass
        else:
            f_approved = approved.strftime(FMT)
        if status in ("delivered", "shipped"):
            f_carrier = carrier.strftime(FMT)
        if status == "delivered":
            f_delivered = delivered.strftime(FMT)
            delivered_idx.append(n)

        orders.append([order_id, customer_id, status, purchase.strftime(FMT), f_approved,
                       f_carrier, f_delivered, estimated.strftime(FMT)])

        # items (none for a few non-delivered orders)
        total_value = 0.0
        if not (status in ("created", "unavailable", "canceled") and rng.random() < 0.7):
            k = rng.choices([1, 2, 3, 4], weights=[88, 9, 2, 1])[0]
            for j in range(1, k + 1):
                prod = rng.choice(products)
                sel = rng.choice(sellers)
                price = round(min(max(rng.lognormvariate(4.0, 0.9), 3), 2500), 2)
                freight = round(8 + price ** 0.3 + rng.random() * 10 + transit_mean * 0.4, 2)
                total_value += price + freight
                items.append([order_id, j, prod[0], sel[0],
                              (purchase + timedelta(days=3)).strftime(FMT), price, freight])

        # payments
        if total_value > 0:
            pay_total = total_value
            r = rng.random()
            if r < 0.03:
                pay_total = round(total_value * 1.07, 2)       # instalment interest
            ptype = wchoice(rng, PAY_TYPES)
            inst = rng.choices(range(1, 11), weights=[50, 12, 10, 8, 5, 4, 3, 3, 2, 3])[0] if ptype == "credit_card" else 1
            if rng.random() < 0.02 and total_value > 30:        # voucher split
                v = round(total_value * 0.3, 2)
                payments.append([order_id, 1, "credit_card", inst, round(pay_total - v, 2)])
                payments.append([order_id, 2, "voucher", 1, v])
            else:
                payments.append([order_id, 1, ptype, inst, round(pay_total, 2)])
        else:
            payments.append([order_id, 1, "credit_card", 1, round(rng.uniform(20, 200), 2)])

        # reviews (~99% of delivered orders, fewer otherwise)
        if (status == "delivered" and rng.random() < 0.99) or rng.random() < 0.3:
            base = delivered if status == "delivered" else purchase + timedelta(days=10)
            created = (base + timedelta(days=1)).replace(hour=0, minute=0, second=0)
            answered = created + timedelta(hours=rng.randint(1, 120))
            score = review_score(rng, delay if status == "delivered" else 10)
            comment = ""
            if rng.random() < 0.3:
                comment = rng.choice(["Chegou bem", "Produto ok, mas demorou", 'Muito bom, "recomendo"',
                                      "Nao gostei,\npessimo prazo", "Entrega rapida"])
            reviews.append([hex_id(rng), order_id, score, "", comment,
                            created.strftime(FMT), answered.strftime(FMT)])
            if rng.random() < 0.006:  # a second, later review for the same order
                reviews.append([hex_id(rng), order_id, rng.randint(1, 5), "", "",
                                created.strftime(FMT), (answered + timedelta(days=2)).strftime(FMT)])

    # --- inject dirt (counts stay well below the alarm tolerances) -----------
    def k(rate, floor=2):
        return max(floor, int(n_orders * rate))

    for i in rng.sample(delivered_idx, k(0.0005)):              # delivered before purchase
        purchase = datetime.strptime(orders[i][3], FMT)
        orders[i][6] = (purchase - timedelta(days=2)).strftime(FMT)
    for i in rng.sample(delivered_idx, k(0.0004)):              # delivered but no delivery date
        orders[i][6] = ""
    for i in rng.sample(range(len(orders)), k(0.0004)):         # unknown customer
        orders[i][1] = hex_id(rng)
    dup_rows = [list(orders[i]) for i in rng.sample(range(len(orders)), k(0.0005, 3))]
    orders_out = orders + dup_rows
    for _ in range(2):                                          # blank order ids
        row = list(rng.choice(orders)); row[0] = ""
        orders_out.append(row)

    for i in rng.sample(range(len(items)), 3):                  # negative price
        items[i][5] = -abs(items[i][5])
    for i in rng.sample(range(len(items)), 2):                  # blank freight
        items[i][6] = ""
    for _ in range(5):                                          # orphan items
        items.append([hex_id(rng), 1, products[0][0], sellers[0][0], "", 10.0, 5.0])
    for _ in range(3):                                          # orphan payments
        payments.append([hex_id(rng), 1, "credit_card", 1, 50.0])
    for _ in range(2):                                          # orphan reviews
        reviews.append([hex_id(rng), hex_id(rng), 4, "", "", "2018-01-01 00:00:00", "2018-01-02 10:00:00"])
    for i, bad in zip(rng.sample(range(len(reviews)), 3), (0, 6, "")):  # invalid scores
        reviews[i][2] = bad

    # --- geolocation: several noisy rows per zip prefix ----------------------
    zips = {c[2] for c in customers} | {s[1] for s in sellers}
    geo = []
    for z in sorted(zips):
        lat, lng = rng.uniform(-30, -3), rng.uniform(-58, -35)
        for _ in range(rng.randint(1, 4)):
            geo.append([z, round(lat + rng.gauss(0, .01), 6), round(lng + rng.gauss(0, .01), 6),
                        "city", rng.choice(state_list)])

    # --- write -------------------------------------------------------------
    write_csv(out / "olist_customers_dataset.csv",
              ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"],
              customers)
    write_csv(out / "olist_orders_dataset.csv",
              ["order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
               "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"],
              orders_out)
    write_csv(out / "olist_order_items_dataset.csv",
              ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"],
              items)
    write_csv(out / "olist_order_payments_dataset.csv",
              ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"], payments)
    write_csv(out / "olist_order_reviews_dataset.csv",
              ["review_id", "order_id", "review_score", "review_comment_title", "review_comment_message",
               "review_creation_date", "review_answer_timestamp"], reviews)
    write_csv(out / "olist_products_dataset.csv",
              ["product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
               "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm",
               "product_width_cm"], products)
    write_csv(out / "olist_sellers_dataset.csv",
              ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"], sellers)
    write_csv(out / "olist_geolocation_dataset.csv",
              ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city",
               "geolocation_state"], geo)
    write_csv(out / "product_category_name_translation.csv",
              ["product_category_name", "product_category_name_english"],
              [(pt, en) for pt, en in CATEGORIES.items() if en])
    (out / "SYNTHETIC_DATA.txt").write_text(
        "Synthetic data generated by tools/make_synthetic_data.py. Not real Olist data.\n")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/synthetic")
    ap.add_argument("--orders", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    print("wrote", generate(a.out, a.orders, a.seed))
