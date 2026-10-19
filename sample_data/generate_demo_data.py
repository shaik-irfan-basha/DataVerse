"""
sample_data/generate_demo_data.py - Deterministic Demo Dataset Generator for DataVerse

Generates realistic, coherent retail e-commerce datasets:
- customers.csv (~100 rows)
- products.csv (~40 rows)
- orders.csv (~250 rows)
- customers_dirty.csv (contains duplicate rows and dirty formatting for data cleaning exercises)
- retail_demo.sqlite (pre-packaged multi-table SQLite database with explicit PK/FK constraints)
- example_queries.sql (canonical SQL queries for testing and demo walkthroughs)

Deterministic: Uses fixed seed (SEED = 42) to produce identical outputs on every run.
"""

import os
import csv
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
OUTPUT_DIR = Path(__file__).resolve().parent

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Carol", "Kevin", "Amanda", "Brian", "Melissa", "George", "Deborah",
    "Edward", "Stephanie", "Ronald", "Rebecca", "Timothy", "Sharon", "Jason", "Laura",
    "Jeffrey", "Cynthia", "Ryan", "Kathleen", "Jacob", "Amy", "Gary", "Shirley",
    "Nicholas", "Angela", "Eric", "Helen", "Jonathan", "Anna", "Stephen", "Brenda",
    "Larry", "Pamela", "Justin", "Nicole", "Scott", "Emma", "Brandon", "Samantha",
    "Benjamin", "Katherine", "Samuel", "Christine", "Gregory", "Debra", "Frank", "Rachel",
    "Alexander", "Catherine", "Raymond", "Carolyn", "Patrick", "Janet", "Jack", "Ruth",
    "Dennis", "Maria", "Jerry", "Heather"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas",
    "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White",
    "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young",
    "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker",
    "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales", "Murphy",
    "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson", "Bailey",
    "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson",
    "Watson", "Brooks", "Chavez", "Wood", "Bennett", "Gray", "Mendoza", "Ruiz",
    "Hughes", "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers", "Long",
    "Ross", "Foster", "Jimenez", "Powell"
]

CITIES_METRO = [
    ("New York", "NY", "10001"),
    ("Los Angeles", "CA", "90001"),
    ("Chicago", "IL", "60601"),
    ("Houston", "TX", "77001"),
    ("Phoenix", "AZ", "85001"),
    ("Philadelphia", "PA", "19101"),
    ("San Antonio", "TX", "78201"),
    ("San Diego", "CA", "92101"),
    ("Dallas", "TX", "75201"),
    ("San Jose", "CA", "95101"),
    ("Austin", "TX", "78701"),
    ("Jacksonville", "FL", "32099"),
    ("San Francisco", "CA", "94101"),
    ("Columbus", "OH", "43201"),
    ("Seattle", "WA", "98101"),
    ("Denver", "CO", "80201"),
    ("Boston", "MA", "02101"),
    ("Miami", "FL", "33101"),
    ("Atlanta", "GA", "30301"),
    ("Portland", "OR", "97201")
]

PRODUCTS_CATALOG = [
    # Electronics (12)
    ("Wireless Noise-Cancelling Headphones", "Electronics", 199.99, 85.00, 150, "Active"),
    ("Ultra-Slim Mechanical Keyboard", "Electronics", 89.99, 38.00, 85, "Active"),
    ("Ergonomic Wireless Mouse", "Electronics", 49.99, 18.50, 210, "Active"),
    ("4K Ultra HD Webcam", "Electronics", 129.99, 55.00, 60, "Active"),
    ("USB-C Multi-Port Hub", "Electronics", 39.99, 14.00, 320, "Active"),
    ("Portable Bluetooth Speaker", "Electronics", 59.99, 24.00, 110, "Active"),
    ("Smart Home Security Camera", "Electronics", 79.99, 32.00, 95, "Active"),
    ("Fast Wireless Charging Pad", "Electronics", 29.99, 9.50, 180, "Active"),
    ("Gaming Monitor 27-inch", "Electronics", 299.99, 140.00, 45, "Active"),
    ("Noise-Isolating Earbuds", "Electronics", 34.99, 11.00, 240, "Active"),
    ("Dual Monitor Arm Mount", "Electronics", 69.99, 26.00, 75, "Active"),
    ("Compact Power Bank 20000mAh", "Electronics", 44.99, 16.50, 160, "Active"),

    # Apparel & Accessories (10)
    ("Classic Organic Cotton T-Shirt", "Apparel", 24.99, 7.50, 400, "Active"),
    ("Slim-Fit Denim Jeans", "Apparel", 68.00, 22.00, 190, "Active"),
    ("Lightweight Zip Hoodie", "Apparel", 54.99, 19.00, 130, "Active"),
    ("Merino Wool Crewneck Sweater", "Apparel", 88.00, 31.00, 70, "Active"),
    ("Waterproof Breathable Rain Jacket", "Apparel", 119.99, 42.00, 50, "Active"),
    ("Casual Canvas Sneakers", "Apparel", 59.99, 20.00, 120, "Active"),
    ("Leather Everyday Belt", "Apparel", 34.50, 11.00, 85, "Active"),
    ("Polarized Sunglasses", "Apparel", 75.00, 18.00, 95, "Active"),
    ("Athletic Running Shorts", "Apparel", 29.99, 8.50, 210, "Active"),
    ("Thermal Winter Beanie", "Apparel", 19.99, 5.00, 0, "Backorder"),

    # Home & Kitchen (10)
    ("Stainless Steel Pour-Over Kettle", "Home & Kitchen", 42.50, 16.00, 115, "Active"),
    ("Cast Iron Skillet 10-inch", "Home & Kitchen", 36.99, 13.50, 140, "Active"),
    ("Double-Walled Travel Mug", "Home & Kitchen", 24.99, 7.00, 260, "Active"),
    ("Chef's Knife 8-inch", "Home & Kitchen", 79.99, 28.00, 65, "Active"),
    ("Non-Stick Baking Sheet Set", "Home & Kitchen", 32.00, 11.00, 90, "Active"),
    ("Bamboo Cutting Board Trio", "Home & Kitchen", 27.99, 9.00, 180, "Active"),
    ("Electric Milk Frother", "Home & Kitchen", 21.99, 6.50, 150, "Active"),
    ("Cold Brew Coffee Maker", "Home & Kitchen", 29.99, 10.00, 80, "Active"),
    ("Ceramic Dinner Plate Set", "Home & Kitchen", 58.00, 21.00, 40, "Active"),
    ("Airtight Food Storage Containers", "Home & Kitchen", 38.50, 14.00, 175, "Active"),

    # Office & Lifestyle (8)
    ("Hardcover Dotted Journal", "Office Supplies", 16.99, 4.50, 310, "Active"),
    ("Premium Rollerball Pen Set", "Office Supplies", 22.00, 6.00, 250, "Active"),
    ("Adjustable Aluminum Laptop Stand", "Office Supplies", 39.99, 13.00, 105, "Active"),
    ("Desk Mat Blotter Leatherette", "Office Supplies", 26.99, 8.00, 145, "Active"),
    ("Ergonomic Memory Foam Cushion", "Office Supplies", 34.99, 12.00, 90, "Active"),
    ("Cable Management Organizer Box", "Office Supplies", 18.99, 5.50, 200, "Active"),
    ("Minimalist LED Desk Lamp", "Office Supplies", 48.00, 17.00, 70, "Active"),
    ("Water-Resistant Commuter Backpack", "Office Supplies", 89.99, 32.00, 85, "Discontinued")
]


def generate_datasets(output_dir: Path = OUTPUT_DIR):
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    # -------------------------------------------------------------------------
    # 1. Generate Customers (100 rows)
    # -------------------------------------------------------------------------
    customers = []
    base_date = datetime(2023, 1, 15)

    for cid in range(1, 101):
        fn = FIRST_NAMES[cid - 1]
        ln = LAST_NAMES[cid - 1]
        email = f"{fn.lower()}.{ln.lower()}{cid}@example.com"

        # Phone: ~6% missing
        if cid in (12, 28, 45, 63, 79, 94):
            phone = ""
        else:
            phone = f"+1-555-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}"

        city_info = CITIES_METRO[(cid * 7) % len(CITIES_METRO)]
        raw_city, raw_state, raw_zip = city_info

        # Inconsistent whitespace & casing for text-cleaning demo (intentional)
        if cid == 5:
            city = f"  {raw_city}"
        elif cid == 18:
            city = raw_city.lower()
        elif cid == 33:
            city = f"{raw_city}  "
        elif cid == 52:
            city = f" {raw_city.lower()} "
        elif cid == 71:
            city = raw_city.upper()
        else:
            city = raw_city

        # Inconsistent state casing
        if cid in (8, 24, 49, 82):
            state = raw_state.lower()
        else:
            state = raw_state

        # Missing postal codes (~4% missing)
        if cid in (15, 38, 67, 88):
            zip_code = ""
        else:
            zip_code = raw_zip

        # Signup date
        signup_dt = base_date + timedelta(days=(cid * 3) % 450)
        signup_str = signup_dt.strftime("%Y-%m-%d")

        # Customer segment
        if cid <= 15:
            segment = "VIP"
        elif cid <= 40:
            segment = "Premium"
        elif cid >= 85:
            segment = "Enterprise"
        else:
            segment = "Standard"

        customers.append({
            "customer_id": cid,
            "first_name": fn,
            "last_name": ln,
            "email": email,
            "phone": phone,
            "city": city,
            "state": state,
            "postal_code": zip_code,
            "signup_date": signup_str,
            "customer_segment": segment
        })

    # -------------------------------------------------------------------------
    # 2. Generate Products (40 rows)
    # -------------------------------------------------------------------------
    products = []
    for pid, (pname, cat, price, cost, stock, status) in enumerate(PRODUCTS_CATALOG, start=1):
        # Controlled category casing / whitespace issues
        if pid == 3:
            cat_val = f" {cat} "
        elif pid == 14:
            cat_val = cat.lower()
        elif pid == 25:
            cat_val = f"{cat}  "
        else:
            cat_val = cat

        # Missing cost for 3 products
        cost_val = "" if pid in (7, 21, 36) else f"{cost:.2f}"

        products.append({
            "product_id": pid,
            "product_name": pname,
            "category": cat_val,
            "price": f"{price:.2f}",
            "cost": cost_val,
            "stock_quantity": stock,
            "status": status
        })

    # -------------------------------------------------------------------------
    # 3. Generate Orders (250 rows)
    # -------------------------------------------------------------------------
    orders = []
    order_base_date = datetime(2023, 6, 1)
    status_choices = ["Completed", "Completed", "Completed", "Shipped", "Processing", "Cancelled", "Refunded"]
    payment_methods = ["Credit Card", "PayPal", "Bank Transfer", "Gift Card", "Apple Pay"]

    # Active customer pool: IDs 1 to 89 (Leaving customers 90-100 with zero orders for outer join demos)
    active_customers = list(range(1, 90))

    for oid in range(1001, 1251):
        idx = oid - 1001

        # Guarantee every customer 1..89 has at least 1 order, then weight VIPs
        if idx < len(active_customers):
            cid = active_customers[idx]
        elif rng.random() < 0.35:
            cid = rng.randint(1, 15)
        else:
            cid = rng.choice(active_customers)

        # Select product
        pid = rng.randint(1, 40)
        prod = products[pid - 1]
        prod_price = float(prod["price"])

        # Quantity: typically 1..4, with 3 intentional realistic bulk outliers
        if oid == 1042:
            qty = 25  # Bulk corporate event order (outlier)
        elif oid == 1150:
            qty = 40  # Holiday bulk office order (outlier)
        elif oid == 1215:
            qty = 30  # Educational conference order (outlier)
        else:
            qty = rng.choices([1, 2, 3, 4, 5], weights=[50, 25, 12, 8, 5])[0]

        unit_price = prod_price
        total_amount = round(qty * unit_price, 2)

        # Order date
        o_date = order_base_date + timedelta(days=idx % 360, hours=(idx * 7) % 24)
        order_date_str = o_date.strftime("%Y-%m-%d")

        # Status
        status = rng.choice(status_choices)

        # Payment method: ~3% missing
        if oid in (1018, 1077, 1144, 1195, 1238):
            pay_method = ""
        else:
            pay_method = rng.choice(payment_methods)

        # Shipping city matches customer city
        cust = customers[cid - 1]
        shipping_city = cust["city"].strip().title()

        orders.append({
            "order_id": oid,
            "customer_id": cid,
            "product_id": pid,
            "order_date": order_date_str,
            "quantity": qty,
            "unit_price": f"{unit_price:.2f}",
            "total_amount": f"{total_amount:.2f}",
            "status": status,
            "payment_method": pay_method,
            "shipping_city": shipping_city
        })

    # -------------------------------------------------------------------------
    # 4. Generate Dirty Customers Test Fixture (with duplicates and extra noise)
    # -------------------------------------------------------------------------
    dirty_customers = [dict(c) for c in customers]

    # Add exact duplicates
    dirty_customers.append(dict(customers[0]))   # Duplicate of customer 1
    dirty_customers.append(dict(customers[4]))   # Duplicate of customer 5
    dirty_customers.append(dict(customers[19]))  # Duplicate of customer 20

    # Add whitespace / case duplicates with identical email
    dup_modified = dict(customers[10])
    dup_modified["first_name"] = f"  {dup_modified['first_name']}  "
    dup_modified["email"] = dup_modified["email"].upper()
    dirty_customers.append(dup_modified)

    # -------------------------------------------------------------------------
    # 5. Write CSV Files
    # -------------------------------------------------------------------------
    def write_csv(filepath: Path, data: list, fieldnames: list):
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print(f"Generated {filepath.name} ({len(data)} rows)")

    write_csv(output_dir / "customers.csv", customers, list(customers[0].keys()))
    write_csv(output_dir / "products.csv", products, list(products[0].keys()))
    write_csv(output_dir / "orders.csv", orders, list(orders[0].keys()))
    write_csv(output_dir / "customers_dirty.csv", dirty_customers, list(dirty_customers[0].keys()))

    # -------------------------------------------------------------------------
    # 6. Generate Pre-packaged Multi-Table SQLite Database (retail_demo.sqlite)
    # -------------------------------------------------------------------------
    sqlite_path = output_dir / "retail_demo.sqlite"
    if sqlite_path.exists():
        sqlite_path.unlink()

    conn = sqlite3.connect(str(sqlite_path))
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            city TEXT,
            state TEXT,
            postal_code TEXT,
            signup_date TEXT,
            customer_segment TEXT
        );
    """)

    cur.execute("""
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            cost REAL,
            stock_quantity INTEGER NOT NULL,
            status TEXT NOT NULL
        );
    """)

    cur.execute("""
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            order_date TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT NOT NULL,
            payment_method TEXT,
            shipping_city TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );
    """)

    for c in customers:
        cur.execute("""
            INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            c["customer_id"], c["first_name"], c["last_name"], c["email"],
            c["phone"] or None, c["city"], c["state"], c["postal_code"] or None,
            c["signup_date"], c["customer_segment"]
        ))

    for p in products:
        cost_val = float(p["cost"]) if p["cost"] else None
        cur.execute("""
            INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (
            p["product_id"], p["product_name"], p["category"],
            float(p["price"]), cost_val, p["stock_quantity"], p["status"]
        ))

    for o in orders:
        cur.execute("""
            INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            o["order_id"], o["customer_id"], o["product_id"], o["order_date"],
            o["quantity"], float(o["unit_price"]), float(o["total_amount"]),
            o["status"], o["payment_method"] or None, o["shipping_city"]
        ))

    conn.commit()
    conn.close()
    print(f"Generated {sqlite_path.name} (Multi-table SQLite database with explicit PK/FK constraints)")

    # -------------------------------------------------------------------------
    # 7. Generate Example Queries SQL Script
    # -------------------------------------------------------------------------
    sql_path = output_dir / "example_queries.sql"
    sql_content = """-- =============================================================================
-- DataVerse Fictional E-Commerce Demo Queries (Aura Retail)
-- =============================================================================
-- These queries demonstrate DataVerse's relational joins, aggregations,
-- grouping, filtering, and outer join edge cases.
-- =============================================================================

-- 1. Customers with their orders (Basic Relational INNER JOIN)
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    c.email,
    o.order_id,
    o.order_date,
    p.product_name,
    o.quantity,
    o.total_amount,
    o.status
FROM customers c
INNER JOIN orders o ON c.customer_id = o.customer_id
INNER JOIN products p ON o.product_id = p.product_id
ORDER BY o.order_date DESC
LIMIT 50;


-- 2. Total sales and order count by customer (Aggregation & Sorting)
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    c.customer_segment,
    COUNT(o.order_id) AS total_orders,
    ROUND(SUM(o.total_amount), 2) AS total_spend,
    ROUND(AVG(o.total_amount), 2) AS average_order_value
FROM customers c
INNER JOIN orders o ON c.customer_id = o.customer_id
WHERE o.status NOT IN ('Cancelled', 'Refunded')
GROUP BY c.customer_id, c.first_name, c.last_name, c.customer_segment
ORDER BY total_spend DESC;


-- 3. Revenue and units sold by product (Product Performance)
SELECT
    p.product_id,
    p.product_name,
    p.category,
    p.price,
    SUM(o.quantity) AS total_units_sold,
    ROUND(SUM(o.total_amount), 2) AS gross_revenue
FROM products p
LEFT JOIN orders o ON p.product_id = o.product_id AND o.status != 'Cancelled'
GROUP BY p.product_id, p.product_name, p.category, p.price
ORDER BY gross_revenue DESC;


-- 4. Orders and revenue broken down by order status
SELECT
    o.status,
    COUNT(*) AS order_count,
    ROUND(SUM(o.total_amount), 2) AS total_volume,
    ROUND(AVG(o.total_amount), 2) AS avg_order_amount
FROM orders o
GROUP BY o.status
ORDER BY order_count DESC;


-- 5. Inactive customers: Customers with no placed orders (LEFT JOIN / Anti-Join)
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    c.email,
    c.customer_segment,
    c.signup_date
FROM customers c
LEFT JOIN orders o ON c.customer_id = o.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id ASC;


-- 6. Top 5 customers by order count
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    c.email,
    COUNT(o.order_id) AS order_count
FROM customers c
INNER JOIN orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.first_name, c.last_name, c.email
ORDER BY order_count DESC
LIMIT 5;


-- 7. High-value orders / Outliers (> $1,000 total order value)
SELECT
    o.order_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    p.product_name,
    o.quantity,
    o.total_amount,
    o.order_date
FROM orders o
INNER JOIN customers c ON o.customer_id = c.customer_id
INNER JOIN products p ON o.product_id = p.product_id
WHERE o.total_amount >= 1000.00
ORDER BY o.total_amount DESC;
"""
    with open(sql_path, "w", encoding="utf-8") as f:
        f.write(sql_content)
    print(f"Generated {sql_path.name} (Canonical demo SQL script)")


if __name__ == "__main__":
    generate_datasets()
