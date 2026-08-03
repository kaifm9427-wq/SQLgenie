"""Create the demo sandbox database if it does not exist yet.

The repo intentionally ignores *.db files, so a fresh deployment has no
database to query. This module builds the demo schema (customers, products,
orders) with sample data the first time it runs.
"""

import os
from sqlalchemy import create_engine, text

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sandbox.db")
DB_URI = f"sqlite:///{DB_PATH}"


def seed_demo_db(force: bool = False) -> bool:
    """Create sandbox.db with demo tables. Returns True if it (re)built it."""
    if not force and os.path.exists(DB_PATH):
        return False

    engine = create_engine(DB_URI)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS orders;"))
        conn.execute(text("DROP TABLE IF EXISTS customers;"))
        conn.execute(text("DROP TABLE IF EXISTS products;"))

        conn.execute(text("""
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT
            );
        """))
        conn.execute(text("""
            CREATE TABLE products (
                product_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                price REAL
            );
        """))
        conn.execute(text("""
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER,
                total_amount REAL,
                order_date TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
                FOREIGN KEY (product_id) REFERENCES products(product_id)
            );
        """))

        conn.execute(text("""
            INSERT INTO customers (first_name, last_name, email) VALUES
                ('Alice', 'Johnson', 'alice@example.com'),
                ('Bob', 'Smith', 'bob@example.com'),
                ('Charlie', 'Brown', 'charlie@example.com'),
                ('Diana', 'Lee', 'diana@example.com'),
                ('Eve', 'Nguyen', 'eve@example.com');
        """))
        conn.execute(text("""
            INSERT INTO products (name, category, price) VALUES
                ('Wireless Mouse', 'Electronics', 29.99),
                ('Mechanical Keyboard', 'Electronics', 89.99),
                ('USB-C Hub', 'Electronics', 49.99),
                ('Laptop Stand', 'Accessories', 24.99),
                ('Desk Lamp', 'Accessories', 39.99);
        """))
        conn.execute(text("""
            INSERT INTO orders (customer_id, product_id, quantity, total_amount, order_date) VALUES
                (1, 1, 2, 59.98, '2026-01-05'),
                (1, 3, 1, 49.99, '2026-02-11'),
                (2, 2, 1, 89.99, '2026-01-18'),
                (3, 5, 2, 79.98, '2026-02-02'),
                (4, 4, 1, 24.99, '2026-02-20'),
                (4, 2, 1, 89.99, '2026-03-01'),
                (5, 1, 1, 29.99, '2026-03-14'),
                (2, 5, 1, 39.99, '2026-03-22');
        """))

    print(f"Seeded demo database at {DB_PATH}")
    return True


if __name__ == "__main__":
    seed_demo_db(force=True)
