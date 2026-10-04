"""In-memory SQLite database.

The database never exists on disk in clear: it is created or deserialized in
memory and written out only through ``Envelope.reseal``.
"""

from __future__ import annotations

import sqlite3

from .errors import Corrupt

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE accounts (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('checking', 'savings', 'cash', 'credit_card', 'brokerage', 'other')),
    institution     TEXT NOT NULL DEFAULT '',
    opening_balance INTEGER NOT NULL DEFAULT 0,
    opening_date    TEXT NOT NULL,
    archived        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE categories (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    color          TEXT NOT NULL,
    monthly_budget INTEGER CHECK (monthly_budget IS NULL OR monthly_budget >= 0),
    UNIQUE (name, kind)
);

CREATE TABLE transactions (
    id             INTEGER PRIMARY KEY,
    account_id     INTEGER NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    date           TEXT NOT NULL,
    amount         INTEGER NOT NULL,
    payee          TEXT NOT NULL DEFAULT '',
    category_id    INTEGER REFERENCES categories (id) ON DELETE SET NULL,
    note           TEXT NOT NULL DEFAULT '',
    transfer_group TEXT,
    import_hash    TEXT,
    created_at     TEXT NOT NULL,
    UNIQUE (account_id, import_hash)
);
CREATE INDEX transactions_by_date ON transactions (date);
CREATE INDEX transactions_by_account ON transactions (account_id, date);
CREATE INDEX transactions_by_transfer ON transactions (transfer_group);

CREATE TABLE rules (
    id          INTEGER PRIMARY KEY,
    pattern     TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories (id) ON DELETE CASCADE
);

CREATE TABLE assets (
    id           INTEGER PRIMARY KEY,
    symbol       TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ('etf', 'stock', 'bond', 'fund', 'crypto', 'other')),
    region       TEXT NOT NULL CHECK (region IN ('global', 'north_america', 'europe', 'asia_pacific', 'emerging', 'other')),
    price_source TEXT NOT NULL CHECK (price_source IN ('manual', 'yahoo', 'coingecko')),
    source_id    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE trades (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    asset_id    INTEGER NOT NULL REFERENCES assets (id) ON DELETE RESTRICT,
    date        TEXT NOT NULL,
    side        TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity    REAL NOT NULL CHECK (quantity > 0),
    price       REAL NOT NULL CHECK (price >= 0),
    fees        INTEGER NOT NULL DEFAULT 0 CHECK (fees >= 0),
    note        TEXT NOT NULL DEFAULT '',
    import_hash TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE (account_id, import_hash)
);
CREATE INDEX trades_by_asset ON trades (asset_id, date);

CREATE TABLE dividends (
    id         INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    asset_id   INTEGER NOT NULL REFERENCES assets (id) ON DELETE RESTRICT,
    date       TEXT NOT NULL,
    amount     INTEGER NOT NULL CHECK (amount >= 0),
    tax        INTEGER NOT NULL DEFAULT 0 CHECK (tax >= 0),
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE prices (
    asset_id INTEGER NOT NULL REFERENCES assets (id) ON DELETE CASCADE,
    date     TEXT NOT NULL,
    price    REAL NOT NULL CHECK (price >= 0),
    source   TEXT NOT NULL,
    PRIMARY KEY (asset_id, date)
);

-- Every movement of cash, whatever produced it. Account balances and the
-- net worth history are both computed from this view, so they always agree.
-- Trade values are rounded to cents the same way everywhere.
CREATE VIEW cash_flows AS
    SELECT account_id, date, amount, 'transaction' AS source FROM transactions
    UNION ALL
    SELECT account_id, date,
           CASE side
               WHEN 'buy' THEN -(CAST(ROUND(quantity * price * 100) AS INTEGER) + fees)
               ELSE CAST(ROUND(quantity * price * 100) AS INTEGER) - fees
           END,
           'trade'
    FROM trades
    UNION ALL
    SELECT account_id, date, amount - tax, 'dividend' FROM dividends;
"""

DEFAULT_SETTINGS = {
    "currency": "EUR",
    "auto_lock_minutes": "5",
    "offline_mode": "0",
}

DEFAULT_CATEGORIES = [
    ("Salary", "income", "#5bb98c"),
    ("Other income", "income", "#7cc7a4"),
    ("Housing", "expense", "#c98b4a"),
    ("Utilities", "expense", "#d4a24c"),
    ("Groceries", "expense", "#8fb35a"),
    ("Eating out", "expense", "#e07a6a"),
    ("Transport", "expense", "#5f9bd3"),
    ("Health", "expense", "#4fb3b3"),
    ("Shopping", "expense", "#b07cd8"),
    ("Leisure", "expense", "#e39ac0"),
    ("Travel", "expense", "#7d8fe0"),
    ("Subscriptions", "expense", "#a3a3a3"),
    ("Gifts", "expense", "#d97f9f"),
    ("Fees and taxes", "expense", "#8a7f72"),
]


def _configure(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")


def create_database(now: str) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
    _configure(conn)
    conn.executescript(SCHEMA)
    with conn:
        conn.execute("BEGIN")
        conn.execute("INSERT INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        conn.execute("INSERT INTO meta VALUES ('created_at', ?)", (now,))
        conn.executemany("INSERT INTO meta VALUES (?, ?)", DEFAULT_SETTINGS.items())
        conn.executemany("INSERT INTO categories (name, kind, color) VALUES (?, ?, ?)", DEFAULT_CATEGORIES)
    return conn


def load_database(data: bytes) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
    conn.deserialize(data)
    _configure(conn)
    version = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    if version is None or int(version[0]) > SCHEMA_VERSION:
        conn.close()
        raise Corrupt("This vault was created by a newer version of Coffer")
    return conn


def dump_database(conn: sqlite3.Connection) -> bytes:
    return conn.serialize()
