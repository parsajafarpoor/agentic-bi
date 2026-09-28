import os
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from faker import Faker


# -----------------------------
# Configuration
# -----------------------------

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

random.seed(42)
np.random.seed(42)

fake = Faker("fa_IR")
Faker.seed(42)


# -----------------------------
# Database connection
# -----------------------------

print("Connecting to PostgreSQL...")

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

print("Connected successfully.")


# -----------------------------
# Clean existing data
# -----------------------------

print("Cleaning existing data...")

cursor.execute("""
    TRUNCATE TABLE
        sales,
        targets,
        customers,
        products,
        sales_managers,
        regions
    RESTART IDENTITY CASCADE;
""")

conn.commit()


# -----------------------------
# Regions
# -----------------------------

regions = [
    "تهران",
    "مشهد",
    "اصفهان",
    "شیراز",
    "تبریز",
    "رشت",
]

region_ids = []

for region in regions:
    cursor.execute(
        """
        INSERT INTO regions (region_name)
        VALUES (%s)
        RETURNING region_id;
        """,
        (region,)
    )

    region_ids.append(cursor.fetchone()[0])


# -----------------------------
# Sales Managers
# -----------------------------

manager_names = [
    "علی احمدی",
    "محمد رضایی",
    "سارا کریمی",
    "امیر حسینی",
    "نگار محمدی",
    "رضا مرادی",
    "مریم موسوی",
    "حسین اکبری",
]

manager_ids = []

for i, name in enumerate(manager_names):

    region_id = region_ids[i % len(region_ids)]

    cursor.execute(
        """
        INSERT INTO sales_managers
        (manager_name, region_id)
        VALUES (%s, %s)
        RETURNING manager_id;
        """,
        (name, region_id)
    )

    manager_ids.append(cursor.fetchone()[0])


# -----------------------------
# Products
# -----------------------------

products = [
    ("Flash Drive 16GB", "USB Flash", 16, 250000, 160000),
    ("Flash Drive 32GB", "USB Flash", 32, 350000, 220000),
    ("Flash Drive 64GB", "USB Flash", 64, 520000, 330000),
    ("Flash Drive 128GB", "USB Flash", 128, 850000, 550000),
    ("Flash Drive 256GB", "USB Flash", 256, 1450000, 950000),
    ("Flash Drive USB3 32GB", "USB 3.0", 32, 420000, 270000),
    ("Flash Drive USB3 64GB", "USB 3.0", 64, 620000, 400000),
    ("Flash Drive USB3 128GB", "USB 3.0", 128, 980000, 630000),
    ("Flash Drive USB3 256GB", "USB 3.0", 256, 1650000, 1080000),
    ("Type-C Flash 64GB", "Type-C", 64, 700000, 450000),
    ("Type-C Flash 128GB", "Type-C", 128, 1100000, 720000),
    ("Type-C Flash 256GB", "Type-C", 256, 1800000, 1200000),
    ("Metal Flash 64GB", "Premium", 64, 800000, 510000),
    ("Metal Flash 128GB", "Premium", 128, 1250000, 800000),
    ("Metal Flash 256GB", "Premium", 256, 2000000, 1300000),
]

product_ids = []

for product in products:

    cursor.execute(
        """
        INSERT INTO products
        (product_name, category, capacity_gb, unit_price, unit_cost)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING product_id;
        """,
        product
    )

    product_ids.append(cursor.fetchone()[0])


# -----------------------------
# Customers
# -----------------------------

customer_ids = []

cities = {
    1: "تهران",
    2: "مشهد",
    3: "اصفهان",
    4: "شیراز",
    5: "تبریز",
    6: "رشت",
}

for i in range(100):

    region_id = random.choice(region_ids)

    city = cities[region_id]

    customer_name = f"مشتری {i + 1:03d}"

    cursor.execute(
        """
        INSERT INTO customers
        (customer_name, city, region_id)
        VALUES (%s, %s, %s)
        RETURNING customer_id;
        """,
        (customer_name, city, region_id)
    )

    customer_ids.append(cursor.fetchone()[0])


# -----------------------------
# Sales
# -----------------------------

print("Generating one year of sales...")

start_date = date(2025, 1, 1)
end_date = date(2025, 12, 31)

current_date = start_date

sale_count = 0

while current_date <= end_date:

    # Seasonal effect
    month = current_date.month

    seasonal_factor = {
        1: 0.90,
        2: 0.95,
        3: 1.10,
        4: 1.00,
        5: 1.05,
        6: 1.10,
        7: 1.20,
        8: 1.15,
        9: 1.05,
        10: 1.00,
        11: 1.15,
        12: 1.30,
    }[month]

    # Weekends have lower sales
    weekday_factor = 0.65 if current_date.weekday() >= 5 else 1.0

    daily_factor = seasonal_factor * weekday_factor

    # Number of transactions per day
    daily_sales = max(
        20,
        int(np.random.normal(80, 15) * daily_factor)
    )

    for _ in range(daily_sales):

        manager_id = random.choice(manager_ids)

        customer_id = random.choice(customer_ids)

        product_id = random.choice(product_ids)

        product_index = product_ids.index(product_id)

        base_price = products[product_index][3]
        unit_cost = products[product_index][4]

        quantity = max(
            1,
            int(np.random.lognormal(mean=1.0, sigma=0.6))
        )

        discount = round(
            random.uniform(0, 12),
            2
        )

        unit_price = round(
            base_price * (1 - discount / 100),
            2
        )

        total_amount = round(
            quantity * unit_price,
            2
        )

        total_cost = round(
            quantity * unit_cost,
            2
        )

        cursor.execute(
            """
            INSERT INTO sales
            (
                sale_date,
                manager_id,
                customer_id,
                product_id,
                quantity,
                unit_price,
                discount_percent,
                total_amount,
                total_cost
            )
            VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                current_date,
                manager_id,
                customer_id,
                product_id,
                quantity,
                unit_price,
                discount,
                total_amount,
                total_cost,
            )
        )

        sale_count += 1

    current_date += timedelta(days=1)

    if current_date.day == 1:
        print(
            f"Processed {current_date.strftime('%Y-%m')} "
            f"| Sales records: {sale_count:,}"
        )


# -----------------------------
# Monthly Targets
# -----------------------------

print("Generating monthly targets...")

for manager_id in manager_ids:

    manager_factor = random.uniform(0.85, 1.20)

    for month in range(1, 13):

        target_date = date(2025, month, 1)

        base_target = 100_000_000

        seasonal_target = {
            1: 0.90,
            2: 0.95,
            3: 1.10,
            4: 1.00,
            5: 1.05,
            6: 1.10,
            7: 1.15,
            8: 1.10,
            9: 1.00,
            10: 1.00,
            11: 1.15,
            12: 1.25,
        }[month]

        target_amount = round(
            base_target
            * manager_factor
            * seasonal_target,
            2
        )

        cursor.execute(
            """
            INSERT INTO targets
            (
                manager_id,
                target_month,
                target_amount
            )
            VALUES (%s, %s, %s);
            """,
            (
                manager_id,
                target_date,
                target_amount,
            )
        )


# -----------------------------
# Commit
# -----------------------------

conn.commit()

print()
print("=" * 50)
print("DATA GENERATION COMPLETED")
print("=" * 50)
print(f"Sales records generated: {sale_count:,}")
print("Regions: 6")
print("Managers: 8")
print("Customers: 100")
print("Products: 15")
print("Targets: 96")
print("=" * 50)


cursor.close()
conn.close()