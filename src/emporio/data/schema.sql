PRAGMA foreign_keys = ON;

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT
);

CREATE TABLE products (
    product_id     INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    name_search    TEXT NOT NULL,
    category_id    INTEGER NOT NULL REFERENCES categories(category_id),
    price_brl      REAL NOT NULL CHECK (price_brl > 0),
    stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
    status         TEXT NOT NULL CHECK (status IN ('active', 'discontinued', 'coming_soon')),
    description    TEXT,
    specs          TEXT,
    created_at     TEXT
);

CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    phone        TEXT NOT NULL,
    phone_digits TEXT NOT NULL,
    email        TEXT NOT NULL UNIQUE,
    city         TEXT
);

CREATE TABLE orders (
    order_id           INTEGER PRIMARY KEY,
    customer_id        INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date         TEXT NOT NULL,
    status             TEXT NOT NULL,
    total_brl          REAL NOT NULL,
    payment_method     TEXT NOT NULL,
    tracking_code      TEXT,
    estimated_delivery TEXT,
    notes              TEXT
);

CREATE TABLE order_items (
    order_id   INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE promotions (
    promotion_id     INTEGER PRIMARY KEY,
    product_id       INTEGER NOT NULL REFERENCES products(product_id),
    discount_percent REAL NOT NULL CHECK (discount_percent > 0 AND discount_percent < 100),
    description      TEXT,
    is_active        INTEGER NOT NULL CHECK (is_active IN (0, 1))
);

CREATE UNIQUE INDEX one_active_promotion_per_product
    ON promotions(product_id) WHERE is_active = 1;

CREATE TABLE policy_sections (
    slug    TEXT PRIMARY KEY,
    number  INTEGER NOT NULL UNIQUE,
    title   TEXT NOT NULL,
    content TEXT NOT NULL
);
