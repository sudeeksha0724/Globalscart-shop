from __future__ import annotations

import argparse
import os
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker


@dataclass(frozen=True)
class ScaleConfig:
    geos: int
    fcs: int
    customers: int
    products: int
    orders: int
    max_items_per_order: int


SCALES: dict[str, ScaleConfig] = {
    "small": ScaleConfig(geos=20, fcs=12, customers=25000, products=2000, orders=60000, max_items_per_order=5),
    "medium": ScaleConfig(geos=35, fcs=20, customers=90000, products=6000, orders=220000, max_items_per_order=6),
    "large": ScaleConfig(geos=60, fcs=35, customers=250000, products=15000, orders=700000, max_items_per_order=7),
}


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _date_dim(start: date, end: date) -> pd.DataFrame:
    dts = pd.date_range(start=start, end=end, freq="D")
    df = pd.DataFrame({"date_value": dts.date})
    df["date_id"] = df["date_value"].apply(lambda x: int(x.strftime("%Y%m%d")))
    df["year"] = pd.to_datetime(df["date_value"]).dt.year
    df["quarter"] = pd.to_datetime(df["date_value"]).dt.quarter
    df["month"] = pd.to_datetime(df["date_value"]).dt.month
    df["month_name"] = pd.to_datetime(df["date_value"]).dt.strftime("%B")
    df["week_of_year"] = pd.to_datetime(df["date_value"]).dt.isocalendar().week.astype(int)
    df["day_of_month"] = pd.to_datetime(df["date_value"]).dt.day
    df["day_of_week"] = pd.to_datetime(df["date_value"]).dt.dayofweek + 1
    df["day_name"] = pd.to_datetime(df["date_value"]).dt.strftime("%A")
    df["is_weekend"] = df["day_of_week"].isin([6, 7])
    return df[[
        "date_id",
        "date_value",
        "year",
        "quarter",
        "month",
        "month_name",
        "week_of_year",
        "day_of_month",
        "day_of_week",
        "day_name",
        "is_weekend",
    ]]


def _geo_dim(fake: Faker, n: int, rng: random.Random) -> pd.DataFrame:
    now_ts = datetime.utcnow().replace(microsecond=0)
    countries = [
        ("United States", "North America", "USD"),
        ("Canada", "North America", "CAD"),
        ("United Kingdom", "Europe", "GBP"),
        ("Germany", "Europe", "EUR"),
        ("France", "Europe", "EUR"),
        ("India", "APAC", "INR"),
        ("Singapore", "APAC", "SGD"),
        ("Australia", "APAC", "AUD"),
        ("Japan", "APAC", "JPY"),
        ("Brazil", "LATAM", "BRL"),
    ]

    rows = []
    for geo_id in range(1, n + 1):
        country, region, currency = countries[rng.randrange(len(countries))]
        rows.append(
            {
                "geo_id": geo_id,
                "country": country,
                "region": region,
                "city": fake.city(),
                "currency": currency,
                "created_at": now_ts,
                "updated_at": now_ts,
            }
        )
    return pd.DataFrame(rows)


def _fc_dim(fake: Faker, geos: pd.DataFrame, n: int, rng: random.Random) -> pd.DataFrame:
    now_ts = datetime.utcnow().replace(microsecond=0)
    tz_by_region = {
        "North America": "America/New_York",
        "Europe": "Europe/London",
        "APAC": "Asia/Kolkata",
        "LATAM": "America/Sao_Paulo",
    }
    rows = []
    geo_ids = geos["geo_id"].tolist()
    geo_region = geos.set_index("geo_id")["region"].to_dict()
    for fc_id in range(1, n + 1):
        geo_id = geo_ids[rng.randrange(len(geo_ids))]
        region = geo_region[geo_id]
        rows.append(
            {
                "fc_id": fc_id,
                "fc_name": f"FC-{fake.lexify(text='????').upper()}-{fc_id}",
                "geo_id": geo_id,
                "timezone": tz_by_region.get(region, "UTC"),
                "created_at": now_ts,
                "updated_at": now_ts,
            }
        )
    return pd.DataFrame(rows)


def _customer_dim(fake: Faker, geos: pd.DataFrame, n: int, start_dt: datetime, end_dt: datetime, rng: random.Random) -> pd.DataFrame:
    channels = ["ORGANIC", "PAID_SEARCH", "AFFILIATES", "EMAIL", "SOCIAL"]
    geo_ids = geos["geo_id"].tolist()

    rows = []
    seconds_range = int((end_dt - start_dt).total_seconds())
    for customer_id in range(1, n + 1):
        created_ts = start_dt + timedelta(seconds=rng.randrange(max(seconds_range, 1)))
        rows.append(
            {
                "customer_id": customer_id,
                "customer_created_ts": created_ts,
                "geo_id": geo_ids[rng.randrange(len(geo_ids))],
                "acquisition_channel": channels[rng.randrange(len(channels))],
                "created_at": created_ts,
                "updated_at": created_ts,
            }
        )
    return pd.DataFrame(rows)


def _product_dim(fake: Faker, n: int, rng: random.Random) -> pd.DataFrame:
    now_ts = datetime.utcnow().replace(microsecond=0)
    catalog = {
        "ELECTRONICS": {
            "MOBILE": ("Smartphone", (8999, 89999), ["Samsung", "Apple", "Xiaomi", "OnePlus", "Motorola", "Realme"]),
            "LAPTOP": ("Laptop", (29999, 179999), ["Dell", "HP", "Lenovo", "ASUS", "Acer", "Apple"]),
            "AUDIO": ("Audio", (999, 29999), ["Sony", "JBL", "boAt", "Bose", "Sennheiser"]),
            "TV": ("Smart TV", (19999, 149999), ["Samsung", "LG", "Sony", "TCL", "Mi"]),
            "ACCESSORIES": ("Accessory", (299, 9999), ["Anker", "Spigen", "boAt", "Portronics", "Mi"]),
        },
        "APPLIANCES": {
            "KITCHEN": ("Appliance", (1499, 49999), ["Philips", "Prestige", "Bajaj", "Havells", "Morphy Richards"]),
            "COOLING": ("Appliance", (24999, 89999), ["LG", "Samsung", "Whirlpool", "Haier", "Panasonic"]),
            "LAUNDRY": ("Appliance", (18999, 69999), ["IFB", "LG", "Samsung", "Bosch", "Whirlpool"]),
        },
        "HOME": {
            "FURNITURE": ("Home", (1999, 59999), ["IKEA", "Urban Ladder", "Home Centre", "Wakefit"]),
            "DECOR": ("Home", (299, 12999), ["IKEA", "Home Centre", "DecoCraft", "Urban Ladder"]),
            "BED_BATH": ("Home", (199, 7999), ["Spaces", "Bombay Dyeing", "D'Decor", "Wakefit"]),
        },
        "BEAUTY": {
            "SKINCARE": ("Beauty", (149, 2499), ["Nivea", "Neutrogena", "Minimalist", "Mamaearth", "L'Oreal"]),
            "HAIRCARE": ("Beauty", (129, 1999), ["Dove", "Tresemme", "L'Oreal", "Head & Shoulders", "WOW"]),
            "MAKEUP": ("Beauty", (199, 2999), ["Lakme", "Maybelline", "Nykaa", "L'Oreal"]),
        },
        "GROCERY": {
            "STAPLES": ("Grocery", (99, 1999), ["Tata", "Aashirvaad", "Fortune", "Saffola", "Patanjali"]),
            "SNACKS": ("Grocery", (10, 399), ["Lay's", "Haldiram's", "Kurkure", "Britannia", "Parle"]),
            "BEVERAGES": ("Grocery", (20, 999), ["Nescafe", "Tata Tea", "Bru", "Red Bull", "Paper Boat"]),
        },
    }

    mobile_specs = ["64GB", "128GB", "256GB"]
    laptop_specs = ["i5", "i7", "Ryzen 5", "Ryzen 7"]
    audio_specs = ["Wireless", "Bluetooth", "Noise Cancelling"]
    tv_sizes = ["43-inch", "50-inch", "55-inch", "65-inch"]
    acc_types = ["Power Bank", "USB-C Charger", "Wireless Mouse", "Keyboard", "Smartwatch", "Fitness Band"]
    kitchen_types = ["Air Fryer", "Mixer Grinder", "Induction Cooktop", "Microwave", "Coffee Maker"]
    cooling_types = ["Refrigerator", "Air Conditioner", "Air Cooler"]
    laundry_types = ["Washing Machine", "Dryer"]
    furniture_types = ["Office Chair", "Study Table", "Sofa", "Bookshelf", "Bed"]
    decor_types = ["Wall Art", "Table Lamp", "Rug", "Curtains", "Clock"]
    bedbath_types = ["Bedsheet Set", "Pillow", "Comforter", "Towel Set"]
    skincare_types = ["Face Wash", "Moisturizer", "Sunscreen", "Serum"]
    haircare_types = ["Shampoo", "Conditioner", "Hair Oil", "Hair Mask"]
    makeup_types = ["Lipstick", "Foundation", "Mascara", "Eyeliner"]
    staples_types = ["Basmati Rice", "Atta", "Toor Dal", "Olive Oil", "Ghee"]
    snacks_types = ["Chips", "Namkeen", "Biscuits", "Chocolate"]
    beverages_types = ["Coffee", "Tea", "Energy Drink", "Juice"]

    rows = []
    for product_id in range(1, n + 1):
        l1 = list(catalog.keys())[rng.randrange(len(catalog))]
        l2 = list(catalog[l1].keys())[rng.randrange(len(catalog[l1]))]
        _, price_range, brand_pool = catalog[l1][l2]
        brand = brand_pool[rng.randrange(len(brand_pool))]

        list_price = round(rng.uniform(price_range[0], price_range[1]), 2)
        markup = rng.uniform(1.18, 1.75)
        unit_cost = round(list_price / markup, 2)

        if l1 == "ELECTRONICS" and l2 == "MOBILE":
            model = f"{rng.choice(['A', 'M', 'S', 'X'])}{rng.randrange(10, 99)}"
            product_name = f"{brand} {model} 5G Smartphone ({rng.choice(mobile_specs)})"
        elif l1 == "ELECTRONICS" and l2 == "LAPTOP":
            series = rng.choice(["Inspiron", "Pavilion", "IdeaPad", "VivoBook", "Aspire", "MacBook"])
            product_name = f"{brand} {series} {rng.choice(laptop_specs)} Laptop"
        elif l1 == "ELECTRONICS" and l2 == "AUDIO":
            kind = rng.choice(["Earbuds", "Headphones", "Speaker", "Soundbar"])
            product_name = f"{brand} {rng.choice(audio_specs)} {kind}"
        elif l1 == "ELECTRONICS" and l2 == "TV":
            product_name = f"{brand} {rng.choice(tv_sizes)} 4K Smart TV"
        elif l1 == "ELECTRONICS" and l2 == "ACCESSORIES":
            product_name = f"{brand} {rng.choice(acc_types)}"
        elif l1 == "APPLIANCES" and l2 == "KITCHEN":
            product_name = f"{brand} {rng.choice(kitchen_types)}"
        elif l1 == "APPLIANCES" and l2 == "COOLING":
            product_name = f"{brand} {rng.choice(cooling_types)}"
        elif l1 == "APPLIANCES" and l2 == "LAUNDRY":
            product_name = f"{brand} {rng.choice(laundry_types)}"
        elif l1 == "HOME" and l2 == "FURNITURE":
            product_name = f"{brand} {rng.choice(furniture_types)}"
        elif l1 == "HOME" and l2 == "DECOR":
            product_name = f"{brand} {rng.choice(decor_types)}"
        elif l1 == "HOME" and l2 == "BED_BATH":
            product_name = f"{brand} {rng.choice(bedbath_types)}"
        elif l1 == "BEAUTY" and l2 == "SKINCARE":
            product_name = f"{brand} {rng.choice(skincare_types)}"
        elif l1 == "BEAUTY" and l2 == "HAIRCARE":
            product_name = f"{brand} {rng.choice(haircare_types)}"
        elif l1 == "BEAUTY" and l2 == "MAKEUP":
            product_name = f"{brand} {rng.choice(makeup_types)}"
        elif l1 == "GROCERY" and l2 == "STAPLES":
            product_name = f"{brand} {rng.choice(staples_types)}"
        elif l1 == "GROCERY" and l2 == "SNACKS":
            product_name = f"{brand} {rng.choice(snacks_types)}"
        else:
            product_name = f"{brand} {rng.choice(beverages_types)}"

        rows.append(
            {
                "product_id": product_id,
                "sku": f"SKU-{product_id:07d}",
                "product_name": product_name[:200],
                "category_l1": l1,
                "category_l2": l2,
                "brand": brand,
                "unit_cost": unit_cost,
                "list_price": list_price,
                "created_at": now_ts,
                "updated_at": now_ts,
            }
        )

    return pd.DataFrame(rows)


def _generate_orders(
    customers: pd.DataFrame,
    geos: pd.DataFrame,
    products: pd.DataFrame,
    scale: ScaleConfig,
    start_dt: datetime,
    end_dt: datetime,
    rng: random.Random,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    np_rng = np.random.default_rng(seed)

    order_statuses = ["CREATED", "CANCELLED", "DELIVERED", "COMPLETED"]
    status_probs = [0.05, 0.08, 0.52, 0.35]

    payment_methods = ["CARD", "UPI", "WALLET", "COD"]
    providers = ["VISA", "MASTERCARD", "PAYPAL", "STRIPE", "RAZORPAY"]

    carriers = ["DHL", "FEDEX", "UPS", "LOCAL_XPRESS"]

    channels = ["WEB", "APP"]

    geo_currency = geos.set_index("geo_id")["currency"].to_dict()

    customer_ids = customers["customer_id"].tolist()
    customer_geo = customers.set_index("customer_id")["geo_id"].to_dict()

    product_ids = products["product_id"].tolist()
    product_cost = products.set_index("product_id")["unit_cost"].to_dict()
    product_list_price = products.set_index("product_id")["list_price"].to_dict()
    product_cat1 = products.set_index("product_id")["category_l1"].to_dict()

    order_rows = []
    item_rows = []
    payment_rows = []
    shipment_rows = []
    return_rows = []
    funnel_rows = []

    seconds_range = int((end_dt - start_dt).total_seconds())

    order_item_id = 1
    payment_id = 1
    shipment_id = 1
    return_id = 1
    event_id = 1

    for order_id in range(1, scale.orders + 1):
        customer_id = customer_ids[rng.randrange(len(customer_ids))]
        geo_id = customer_geo[customer_id]
        currency = geo_currency[geo_id]

        order_ts = start_dt + timedelta(seconds=rng.randrange(max(seconds_range, 1)))

        month = order_ts.month
        seasonal_boost = 1.0
        if month in (11, 12):
            seasonal_boost = 1.25
        if month in (6, 7):
            seasonal_boost = 1.08

        status = np_rng.choice(order_statuses, p=status_probs)
        channel = channels[rng.randrange(len(channels))]

        device = "MOBILE" if (channel == "APP" or rng.random() < 0.65) else "DESKTOP"
        session_id = f"sess_{order_id}_{rng.randrange(1_000_000_000):09d}"

        num_items = rng.randint(1, scale.max_items_per_order)
        chosen_products = [product_ids[rng.randrange(len(product_ids))] for _ in range(num_items)]

        gross = 0.0
        total_discount = 0.0
        total_tax = 0.0
        net = 0.0

        high_discount_period = month in (11, 12)

        for pid in chosen_products:
            qty = rng.randint(1, 3)
            list_price = float(product_list_price[pid])
            cost = float(product_cost[pid])

            base_discount = rng.uniform(0.02, 0.18)
            if high_discount_period:
                base_discount += rng.uniform(0.05, 0.18)

            if product_cat1[pid] in ("APPAREL", "BEAUTY"):
                base_discount += rng.uniform(0.02, 0.08)

            base_discount = min(base_discount, 0.55)

            unit_sell = round(list_price * (1.0 - base_discount), 2)
            line_gross = round(list_price * qty, 2)
            line_discount = round((list_price - unit_sell) * qty, 2)
            line_tax = round(0.07 * (unit_sell * qty), 2)
            line_net = round((unit_sell * qty) + line_tax, 2)

            gross += line_gross
            total_discount += line_discount
            total_tax += line_tax
            net += line_net

            item_rows.append(
                {
                    "order_item_id": order_item_id,
                    "order_id": order_id,
                    "product_id": pid,
                    "qty": qty,
                    "unit_list_price": round(list_price, 2),
                    "unit_sell_price": unit_sell,
                    "unit_cost": round(cost, 2),
                    "line_discount": line_discount,
                    "line_tax": line_tax,
                    "line_net_revenue": line_net,
                    "created_at": order_ts,
                    "updated_at": order_ts,
                }
            )
            order_item_id += 1

        session_start = order_ts - timedelta(minutes=rng.randint(4, 90))
        viewed_products = list(dict.fromkeys(chosen_products + [product_ids[rng.randrange(len(product_ids))] for _ in range(rng.randint(0, 2))]))
        t = session_start
        for pid in viewed_products:
            for _ in range(rng.randint(1, 3)):
                t = t + timedelta(seconds=rng.randint(5, 35))
                funnel_rows.append(
                    {
                        "event_id": event_id,
                        "event_ts": t,
                        "session_id": session_id,
                        "customer_id": customer_id,
                        "product_id": int(pid),
                        "order_id": None,
                        "stage": "VIEW_PRODUCT",
                        "channel": channel,
                        "device": device,
                        "failure_reason": None,
                    }
                )
                event_id += 1

        for pid in list(dict.fromkeys(chosen_products)):
            if rng.random() < 0.92:
                t = t + timedelta(seconds=rng.randint(8, 55))
                funnel_rows.append(
                    {
                        "event_id": event_id,
                        "event_ts": t,
                        "session_id": session_id,
                        "customer_id": customer_id,
                        "product_id": int(pid),
                        "order_id": None,
                        "stage": "ADD_TO_CART",
                        "channel": channel,
                        "device": device,
                        "failure_reason": None,
                    }
                )
                event_id += 1

        t = t + timedelta(seconds=rng.randint(10, 60))
        funnel_rows.append(
            {
                "event_id": event_id,
                "event_ts": t,
                "session_id": session_id,
                "customer_id": customer_id,
                "product_id": None,
                "order_id": None,
                "stage": "VIEW_CART",
                "channel": channel,
                "device": device,
                "failure_reason": None,
            }
        )
        event_id += 1

        t = t + timedelta(seconds=rng.randint(12, 80))
        funnel_rows.append(
            {
                "event_id": event_id,
                "event_ts": t,
                "session_id": session_id,
                "customer_id": customer_id,
                "product_id": None,
                "order_id": None,
                "stage": "CHECKOUT_STARTED",
                "channel": channel,
                "device": device,
                "failure_reason": None,
            }
        )
        event_id += 1

        gross = round(gross * seasonal_boost, 2)
        total_discount = round(total_discount * seasonal_boost, 2)
        total_tax = round(total_tax * seasonal_boost, 2)
        net = round(net * seasonal_boost, 2)

        pay_method = payment_methods[rng.randrange(len(payment_methods))]
        provider = providers[rng.randrange(len(providers))]

        payment_status = "CAPTURED"
        failure_reason = None
        refund_amount = 0.0
        chargeback_flag = False

        if status == "CANCELLED":
            payment_status = np_rng.choice(["FAILED", "DECLINED"], p=[0.55, 0.45])
            failure_reason = np_rng.choice(["INSUFFICIENT_FUNDS", "NETWORK_ERROR", "FRAUD_FLAG", "BANK_DECLINE"]) 
        else:
            if pay_method == "COD" and rng.random() < 0.03:
                payment_status = "DECLINED"
                failure_reason = "COD_RTO"
                status = "CANCELLED"

        t = t + timedelta(seconds=rng.randint(10, 75))
        funnel_rows.append(
            {
                "event_id": event_id,
                "event_ts": t,
                "session_id": session_id,
                "customer_id": customer_id,
                "product_id": None,
                "order_id": order_id,
                "stage": "PAYMENT_ATTEMPTED",
                "channel": channel,
                "device": device,
                "failure_reason": None,
            }
        )
        event_id += 1

        if payment_status in ("FAILED", "DECLINED"):
            t = t + timedelta(seconds=rng.randint(5, 45))
            funnel_rows.append(
                {
                    "event_id": event_id,
                    "event_ts": t,
                    "session_id": session_id,
                    "customer_id": customer_id,
                    "product_id": None,
                    "order_id": order_id,
                    "stage": "PAYMENT_FAILED",
                    "channel": channel,
                    "device": device,
                    "failure_reason": str(failure_reason) if failure_reason is not None else None,
                }
            )
            event_id += 1
        else:
            t = t + timedelta(seconds=rng.randint(5, 45))
            funnel_rows.append(
                {
                    "event_id": event_id,
                    "event_ts": t,
                    "session_id": session_id,
                    "customer_id": customer_id,
                    "product_id": None,
                    "order_id": order_id,
                    "stage": "ORDER_PLACED",
                    "channel": channel,
                    "device": device,
                    "failure_reason": None,
                }
            )
            event_id += 1

        gateway_fee_amount = 0.0
        if pay_method != "COD" and payment_status not in ("FAILED", "DECLINED"):
            fee_rate = rng.uniform(0.015, 0.025)
            if pay_method == "UPI":
                fee_rate = rng.uniform(0.010, 0.016)
            fixed_fee = rng.uniform(0.0, 6.0)
            gateway_fee_amount = round((net * fee_rate) + fixed_fee, 2)

        order_rows.append(
            {
                "order_id": order_id,
                "customer_id": customer_id,
                "geo_id": geo_id,
                "order_ts": order_ts,
                "order_status": str(status),
                "channel": channel,
                "currency": currency,
                "gross_amount": gross,
                "discount_amount": total_discount,
                "tax_amount": total_tax,
                "net_amount": net,
                "created_at": order_ts,
                "updated_at": order_ts + timedelta(minutes=rng.randint(0, 120)),
            }
        )

        payment_rows.append(
            {
                "payment_id": payment_id,
                "order_id": order_id,
                "payment_method": pay_method,
                "payment_status": payment_status,
                "payment_provider": provider,
                "amount": net,
                "gateway_fee_amount": gateway_fee_amount,
                "authorized_ts": order_ts + timedelta(minutes=rng.randint(0, 10)),
                "captured_ts": None if payment_status in ("FAILED", "DECLINED") else order_ts + timedelta(minutes=rng.randint(5, 30)),
                "failure_reason": failure_reason,
                "refund_amount": refund_amount,
                "chargeback_flag": chargeback_flag,
                "created_at": order_ts,
                "updated_at": order_ts,
            }
        )
        payment_id += 1

    orders = pd.DataFrame(order_rows)
    items = pd.DataFrame(item_rows)
    payments = pd.DataFrame(payment_rows)

    delivered_orders = orders[orders["order_status"].isin(["DELIVERED", "COMPLETED"])].copy()

    fc_ids = list(range(1, scale.fcs + 1))

    for _, row in delivered_orders.iterrows():
        order_id = int(row["order_id"])
        order_ts = pd.to_datetime(row["order_ts"]).to_pydatetime()

        base_ship_cost = float(np_rng.lognormal(mean=2.1, sigma=0.35))
        shipping_cost = round(base_ship_cost, 2)

        fc_id = fc_ids[rng.randrange(len(fc_ids))]
        carrier = carriers[rng.randrange(len(carriers))]

        promised_days = rng.randint(2, 6)
        delivered_delay = rng.choice([0, 0, 0, 1, 1, 2, 3])
        promised_dt = (order_ts + timedelta(days=promised_days)).date()
        delivered_dt = (order_ts + timedelta(days=promised_days + delivered_delay)).date()

        sla_breach = delivered_dt > promised_dt

        shipment_rows.append(
            {
                "shipment_id": shipment_id,
                "order_id": order_id,
                "fc_id": fc_id,
                "carrier": carrier,
                "shipped_ts": order_ts + timedelta(hours=rng.randint(4, 48)),
                "promised_delivery_dt": promised_dt,
                "delivered_dt": delivered_dt,
                "shipping_cost": shipping_cost,
                "sla_breached_flag": bool(sla_breach),
                "created_at": order_ts,
                "updated_at": order_ts,
            }
        )
        shipment_id += 1

    shipments = pd.DataFrame(shipment_rows)

    order_item_map = items.groupby("order_id")["order_item_id"].apply(list).to_dict()
    order_items_for_return = []

    if not shipments.empty:
        shipment_breach = shipments.set_index("order_id")["sla_breached_flag"].to_dict()
    else:
        shipment_breach = {}

    for oid, item_ids in order_item_map.items():
        base_p = 0.028
        if shipment_breach.get(oid, False):
            base_p += 0.035
        if rng.random() < base_p:
            order_items_for_return.append((oid, item_ids[rng.randrange(len(item_ids))]))

    items_by_id = items.set_index("order_item_id")

    reasons = ["DAMAGED", "NOT_AS_DESCRIBED", "SIZE_ISSUE", "LATE_DELIVERY", "QUALITY_ISSUE", "CHANGED_MIND"]

    for oid, order_item_id_val in order_items_for_return:
        it = items_by_id.loc[order_item_id_val]
        pid = int(it["product_id"])
        qty = int(it["qty"])
        line_net = float(it["line_net_revenue"])

        reason = reasons[rng.randrange(len(reasons))]
        if product_cat1[pid] == "APPAREL" and rng.random() < 0.45:
            reason = "SIZE_ISSUE"
        if shipment_breach.get(oid, False) and rng.random() < 0.4:
            reason = "LATE_DELIVERY"

        refund_amount = round(line_net * rng.uniform(0.85, 1.0), 2)
        return_rows.append(
            {
                "return_id": return_id,
                "order_id": int(oid),
                "order_item_id": int(order_item_id_val),
                "product_id": pid,
                "return_ts": pd.to_datetime(orders.loc[orders["order_id"] == oid, "order_ts"].iloc[0]) + timedelta(days=rng.randint(3, 25)),
                "return_reason": reason,
                "refund_amount": refund_amount,
                "return_status": "REFUNDED",
                "restocked_flag": bool(rng.random() < 0.65),
                "created_at": pd.to_datetime(orders.loc[orders["order_id"] == oid, "order_ts"].iloc[0]),
                "updated_at": pd.to_datetime(orders.loc[orders["order_id"] == oid, "order_ts"].iloc[0]),
            }
        )
        return_id += 1

    returns = pd.DataFrame(return_rows)

    if not returns.empty:
        refunds_by_order = returns.groupby("order_id")["refund_amount"].sum().to_dict()
        refund_flags = set(refunds_by_order.keys())
        for i, p in enumerate(payment_rows):
            if p["order_id"] in refund_flags and p["payment_status"] == "CAPTURED":
                p["payment_status"] = "REFUNDED"
                p["refund_amount"] = float(refunds_by_order[p["order_id"]])

                if rng.random() < 0.004:
                    p["chargeback_flag"] = True

        payments = pd.DataFrame(payment_rows)

    extra_browse_sessions = min(int(scale.orders * 0.18), 120_000)
    extra_abandon_sessions = min(int(scale.orders * 0.22), 150_000)

    for sidx in range(extra_browse_sessions + extra_abandon_sessions):
        is_abandon = sidx >= extra_browse_sessions

        sess_ts = start_dt + timedelta(seconds=rng.randrange(max(seconds_range, 1)))
        channel = channels[rng.randrange(len(channels))]
        device = "MOBILE" if (channel == "APP" or rng.random() < 0.65) else "DESKTOP"
        session_id = f"sess_x_{sidx}_{rng.randrange(1_000_000_000):09d}"

        sess_customer_id = None
        if rng.random() < 0.62:
            sess_customer_id = customer_ids[rng.randrange(len(customer_ids))]

        n_products = rng.randint(1, 6 if is_abandon else 4)
        sess_products = [product_ids[rng.randrange(len(product_ids))] for _ in range(n_products)]

        t = sess_ts
        for pid in sess_products:
            for _ in range(rng.randint(1, 3)):
                t = t + timedelta(seconds=rng.randint(6, 40))
                funnel_rows.append(
                    {
                        "event_id": event_id,
                        "event_ts": t,
                        "session_id": session_id,
                        "customer_id": sess_customer_id,
                        "product_id": int(pid),
                        "order_id": None,
                        "stage": "VIEW_PRODUCT",
                        "channel": channel,
                        "device": device,
                        "failure_reason": None,
                    }
                )
                event_id += 1

        if is_abandon:
            for pid in list(dict.fromkeys(sess_products))[: rng.randint(1, min(4, len(sess_products)))]:
                t = t + timedelta(seconds=rng.randint(10, 70))
                funnel_rows.append(
                    {
                        "event_id": event_id,
                        "event_ts": t,
                        "session_id": session_id,
                        "customer_id": sess_customer_id,
                        "product_id": int(pid),
                        "order_id": None,
                        "stage": "ADD_TO_CART",
                        "channel": channel,
                        "device": device,
                        "failure_reason": None,
                    }
                )
                event_id += 1

            if rng.random() < 0.65:
                t = t + timedelta(seconds=rng.randint(10, 75))
                funnel_rows.append(
                    {
                        "event_id": event_id,
                        "event_ts": t,
                        "session_id": session_id,
                        "customer_id": sess_customer_id,
                        "product_id": None,
                        "order_id": None,
                        "stage": "VIEW_CART",
                        "channel": channel,
                        "device": device,
                        "failure_reason": None,
                    }
                )
                event_id += 1

            if rng.random() < 0.35:
                t = t + timedelta(seconds=rng.randint(12, 90))
                funnel_rows.append(
                    {
                        "event_id": event_id,
                        "event_ts": t,
                        "session_id": session_id,
                        "customer_id": sess_customer_id,
                        "product_id": None,
                        "order_id": None,
                        "stage": "CHECKOUT_STARTED",
                        "channel": channel,
                        "device": device,
                        "failure_reason": None,
                    }
                )
                event_id += 1

    funnel_events = pd.DataFrame(funnel_rows)
    if not funnel_events.empty:
        for col in ["event_id", "customer_id", "product_id", "order_id"]:
            if col in funnel_events.columns:
                funnel_events[col] = pd.to_numeric(funnel_events[col], errors="coerce").astype("Int64")

    return orders, items, payments, shipments, returns, funnel_events


def generate(scale_name: str, out_dir: Path, seed: int) -> None:
    if scale_name not in SCALES:
        raise ValueError(f"Unknown scale: {scale_name}. Choose from {list(SCALES.keys())}")

    scale = SCALES[scale_name]

    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)

    _ensure_dir(out_dir)

    end_dt = datetime.utcnow().replace(microsecond=0)
    start_dt = end_dt - timedelta(days=365)

    geos = _geo_dim(fake, scale.geos, rng)
    fcs = _fc_dim(fake, geos, scale.fcs, rng)
    customers = _customer_dim(fake, geos, scale.customers, start_dt=start_dt, end_dt=end_dt, rng=rng)
    products = _product_dim(fake, scale.products, rng)

    date_dim = _date_dim(start=(date.today() - timedelta(days=430)), end=date.today())

    orders, items, payments, shipments, returns, funnel_events = _generate_orders(
        customers=customers,
        geos=geos,
        products=products,
        scale=scale,
        start_dt=start_dt,
        end_dt=end_dt,
        rng=rng,
        seed=seed,
    )

    geos.to_csv(out_dir / "dim_geo.csv", index=False)
    fcs.to_csv(out_dir / "dim_fc.csv", index=False)
    customers.to_csv(out_dir / "dim_customer.csv", index=False)
    products.to_csv(out_dir / "dim_product.csv", index=False)
    date_dim.to_csv(out_dir / "dim_date.csv", index=False)

    orders.to_csv(out_dir / "fact_orders.csv", index=False)
    items.to_csv(out_dir / "fact_order_items.csv", index=False)
    payments.to_csv(out_dir / "fact_payments.csv", index=False)
    funnel_events.to_csv(out_dir / "fact_funnel_events.csv", index=False)
    shipments.to_csv(out_dir / "fact_shipments.csv", index=False)
    returns.to_csv(out_dir / "fact_returns.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="small", choices=list(SCALES.keys()))
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data" / "raw"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    generate(args.scale, Path(args.out), seed=args.seed)


if __name__ == "__main__":
    main()
