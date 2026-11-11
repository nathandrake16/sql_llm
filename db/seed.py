"""
db/seed.py
~~~~~~~~~~
Creates and seeds a small e-commerce SQLite database for testing.
Run once:  python db/seed.py
"""

import os
import sqlite3

DB_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "ecommerce.db")


DDL = """
CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    price       REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    city  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date  TEXT    NOT NULL,   -- ISO-8601: YYYY-MM-DD
    total       REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL,
    unit_price REAL    NOT NULL
);
"""

SEED = """
INSERT INTO categories (name) VALUES
  ('Electronics'), ('Books'), ('Clothing'), ('Home & Garden');

INSERT INTO products (name, category_id, price) VALUES
  ('Wireless Headphones', 1, 79.99),
  ('Mechanical Keyboard',  1, 129.99),
  ('USB-C Hub',            1, 39.99),
  ('Clean Code (book)',    2, 34.99),
  ('Dune (book)',          2, 14.99),
  ('Running Shoes',        3, 89.99),
  ('Winter Jacket',        3, 149.99),
  ('Garden Hose 50ft',     4, 44.99),
  ('LED Desk Lamp',        1, 29.99),
  ('Yoga Mat',             3, 24.99);

INSERT INTO customers (name, email, city) VALUES
  ('Alice Martin',   'alice@example.com',   'New York'),
  ('Bob Chen',       'bob@example.com',     'San Francisco'),
  ('Carol White',    'carol@example.com',   'Chicago'),
  ('David Kim',      'david@example.com',   'Austin'),
  ('Eva Larsson',    'eva@example.com',     'Seattle');

INSERT INTO orders (customer_id, order_date, total) VALUES
  (1, '2024-01-05', 209.98),
  (1, '2024-02-14', 34.99),
  (2, '2024-01-20', 219.98),
  (2, '2024-03-01', 39.99),
  (2, '2024-03-15', 44.99),
  (3, '2024-02-28', 149.99),
  (4, '2024-01-10', 109.98),
  (4, '2024-04-05', 24.99),
  (5, '2024-03-22', 44.99),
  (5, '2024-04-18', 79.99);

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
  (1, 1, 1, 79.99),
  (1, 2, 1, 129.99),
  (2, 4, 1, 34.99),
  (3, 6, 1, 89.99),
  (3, 2, 1, 129.99),
  (4, 3, 1, 39.99),
  (5, 8, 1, 44.99),
  (6, 7, 1, 149.99),
  (7, 1, 1, 79.99),
  (7, 9, 1, 29.99),
  (8, 10,1, 24.99),
  (9, 8, 1, 44.99),
  (10,1, 1, 79.99);
"""


def seed() -> None:
    os.makedirs(DB_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(DDL)

    existing = con.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    if existing == 0:
        con.executescript(SEED)
        con.commit()
        print(f"✅  Database created and seeded at: {DB_PATH}")
    else:
        print(f"ℹ️   Database already seeded at: {DB_PATH}")

    con.close()


if __name__ == "__main__":
    seed()
