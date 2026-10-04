"""Reading and writing records. Every function takes an open connection and
plain dicts; checks live here so the interface can stay thin."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, timezone

from . import validate as v
from .errors import Invalid, NotFound

ACCOUNT_KINDS = ("checking", "savings", "cash", "credit_card", "brokerage", "other")
ASSET_KINDS = ("etf", "stock", "bond", "fund", "crypto", "other")
REGIONS = ("global", "north_america", "europe", "asia_pacific", "emerging", "other")
PRICE_SOURCES = ("manual", "yahoo", "coingecko")
CURRENCIES = ("EUR", "USD", "GBP", "CHF")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rows(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]


def one(conn: sqlite3.Connection, sql: str, params=()) -> dict:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        raise NotFound()
    return dict(row)


# Settings


def get_settings(conn: sqlite3.Connection) -> dict:
    meta = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM meta")}
    return {
        "currency": meta.get("currency", "EUR"),
        "auto_lock_minutes": int(meta.get("auto_lock_minutes", "5")),
        "offline_mode": meta.get("offline_mode", "0") == "1",
        "created_at": meta.get("created_at", ""),
    }


def update_settings(conn: sqlite3.Connection, patch: dict) -> dict:
    values: dict[str, str] = {}
    if "currency" in patch:
        values["currency"] = v.choice(patch["currency"], "currency", CURRENCIES)
    if "auto_lock_minutes" in patch:
        minutes = patch["auto_lock_minutes"]
        if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= 120:
            raise Invalid("Auto-lock must be between 1 and 120 minutes")
        values["auto_lock_minutes"] = str(minutes)
    if "offline_mode" in patch:
        values["offline_mode"] = "1" if patch["offline_mode"] is True else "0"
    with conn:
        conn.execute("BEGIN")
        conn.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", values.items())
    return get_settings(conn)


# Accounts


def list_accounts(conn: sqlite3.Connection, include_archived: bool = True) -> list[dict]:
    sql = """
        SELECT a.*, a.opening_balance + COALESCE(f.total, 0) AS balance,
               COALESCE(f.count, 0) AS movements
        FROM accounts a
        LEFT JOIN (
            SELECT account_id, SUM(amount) AS total, COUNT(*) AS count FROM cash_flows GROUP BY account_id
        ) f ON f.account_id = a.id
    """
    if not include_archived:
        sql += " WHERE a.archived = 0"
    sql += " ORDER BY a.archived, CASE a.kind WHEN 'checking' THEN 0 WHEN 'savings' THEN 1 WHEN 'cash' THEN 2"
    sql += " WHEN 'credit_card' THEN 3 WHEN 'brokerage' THEN 4 ELSE 5 END, a.name"
    accounts = rows(conn.execute(sql))
    for account in accounts:
        account["archived"] = bool(account["archived"])
    return accounts


def save_account(conn: sqlite3.Connection, data: dict) -> dict:
    name = v.text(data, "name", max_length=80)
    kind = v.choice(data.get("kind"), "kind", ACCOUNT_KINDS)
    institution = v.text(data, "institution", required=False, max_length=80)
    opening_balance = v.cents(data.get("opening_balance", 0), "opening_balance")
    opening_date = v.iso_date(data.get("opening_date") or date.today().isoformat(), "opening_date")
    archived = 1 if data.get("archived") is True else 0
    with conn:
        conn.execute("BEGIN")
        if data.get("id"):
            account_id = v.ident(data["id"])
            one(conn, "SELECT id FROM accounts WHERE id = ?", (account_id,))
            conn.execute(
                """UPDATE accounts SET name = ?, kind = ?, institution = ?, opening_balance = ?,
                   opening_date = ?, archived = ? WHERE id = ?""",
                (name, kind, institution, opening_balance, opening_date, archived, account_id),
            )
        else:
            account_id = conn.execute(
                """INSERT INTO accounts (name, kind, institution, opening_balance, opening_date, archived, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, kind, institution, opening_balance, opening_date, archived, now()),
            ).lastrowid
    return next(a for a in list_accounts(conn) if a["id"] == account_id)


def delete_account(conn: sqlite3.Connection, account_id: int) -> None:
    account_id = v.ident(account_id)
    with conn:
        conn.execute("BEGIN")
        # The other half of a transfer lives in another account: remove it too,
        # or that account would show money arriving from nowhere.
        conn.execute(
            """DELETE FROM transactions WHERE transfer_group IN (
                   SELECT transfer_group FROM transactions WHERE account_id = ? AND transfer_group IS NOT NULL)""",
            (account_id,),
        )
        if conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,)).rowcount == 0:
            raise NotFound()


# Categories and rules


def list_categories(conn: sqlite3.Connection) -> list[dict]:
    return rows(
        conn.execute(
            """SELECT c.*, (SELECT COUNT(*) FROM transactions t WHERE t.category_id = c.id) AS usage
               FROM categories c ORDER BY c.kind DESC, c.name"""
        )
    )


def save_category(conn: sqlite3.Connection, data: dict) -> dict:
    name = v.text(data, "name", max_length=60)
    kind = v.choice(data.get("kind"), "kind", ("income", "expense"))
    color = v.text(data, "color", max_length=7)
    if not (len(color) == 7 and color.startswith("#")):
        raise Invalid("Color must look like #a1b2c3")
    budget = data.get("monthly_budget")
    budget = None if budget in (None, "") else v.cents(budget, "monthly_budget", minimum=0)
    if kind == "income":
        budget = None
    try:
        with conn:
            conn.execute("BEGIN")
            if data.get("id"):
                category_id = v.ident(data["id"])
                one(conn, "SELECT id FROM categories WHERE id = ?", (category_id,))
                conn.execute(
                    "UPDATE categories SET name = ?, kind = ?, color = ?, monthly_budget = ? WHERE id = ?",
                    (name, kind, color, budget, category_id),
                )
            else:
                category_id = conn.execute(
                    "INSERT INTO categories (name, kind, color, monthly_budget) VALUES (?, ?, ?, ?)",
                    (name, kind, color, budget),
                ).lastrowid
    except sqlite3.IntegrityError as exc:
        raise Invalid(f"There is already an {kind} category called {name}") from exc
    return one(conn, "SELECT * FROM categories WHERE id = ?", (category_id,))


def delete_category(conn: sqlite3.Connection, category_id: int) -> None:
    with conn:
        conn.execute("BEGIN")
        if conn.execute("DELETE FROM categories WHERE id = ?", (v.ident(category_id),)).rowcount == 0:
            raise NotFound()


def list_rules(conn: sqlite3.Connection) -> list[dict]:
    return rows(
        conn.execute(
            """SELECT r.*, c.name AS category_name, c.color AS category_color
               FROM rules r JOIN categories c ON c.id = r.category_id ORDER BY lower(r.pattern)"""
        )
    )


def save_rule(conn: sqlite3.Connection, data: dict) -> dict:
    pattern = v.text(data, "pattern", max_length=80)
    category_id = v.ident(data.get("category_id"), "category")
    one(conn, "SELECT id FROM categories WHERE id = ?", (category_id,))
    with conn:
        conn.execute("BEGIN")
        if data.get("id"):
            rule_id = v.ident(data["id"])
            if conn.execute(
                "UPDATE rules SET pattern = ?, category_id = ? WHERE id = ?", (pattern, category_id, rule_id)
            ).rowcount == 0:
                raise NotFound()
        else:
            rule_id = conn.execute(
                "INSERT INTO rules (pattern, category_id) VALUES (?, ?)", (pattern, category_id)
            ).lastrowid
    return next(r for r in list_rules(conn) if r["id"] == rule_id)


def delete_rule(conn: sqlite3.Connection, rule_id: int) -> None:
    with conn:
        conn.execute("BEGIN")
        if conn.execute("DELETE FROM rules WHERE id = ?", (v.ident(rule_id),)).rowcount == 0:
            raise NotFound()


def category_for(rules: list[dict], payee: str, amount: int, kinds: dict[int, str]) -> int | None:
    """First rule whose pattern appears in the payee. Income categories only
    take money in; expense categories take both (money in is a refund)."""
    text = payee.lower()
    for rule in rules:
        if rule["pattern"].lower() not in text:
            continue
        if kinds.get(rule["category_id"]) == "income" and amount < 0:
            continue
        return rule["category_id"]
    return None


def apply_rules(conn: sqlite3.Connection) -> int:
    """Categorizes uncategorized, non-transfer transactions."""
    rules = list_rules(conn)
    kinds = {c["id"]: c["kind"] for c in list_categories(conn)}
    changed = 0
    with conn:
        conn.execute("BEGIN")
        for tx in conn.execute(
            "SELECT id, payee, amount FROM transactions WHERE category_id IS NULL AND transfer_group IS NULL"
        ).fetchall():
            category_id = category_for(rules, tx["payee"], tx["amount"], kinds)
            if category_id:
                conn.execute("UPDATE transactions SET category_id = ? WHERE id = ?", (category_id, tx["id"]))
                changed += 1
    return changed


# Transactions


TRANSACTION_SELECT = """
    SELECT t.*, a.name AS account_name, c.name AS category_name, c.color AS category_color,
           o.account_id AS counter_account_id, oa.name AS counter_account_name
    FROM transactions t
    JOIN accounts a ON a.id = t.account_id
    LEFT JOIN categories c ON c.id = t.category_id
    LEFT JOIN transactions o ON o.transfer_group = t.transfer_group AND o.id != t.id
    LEFT JOIN accounts oa ON oa.id = o.account_id
"""


def list_transactions(conn: sqlite3.Connection, query: dict) -> dict:
    where, params = [], []
    if query.get("account_id"):
        where.append("t.account_id = ?")
        params.append(v.ident(query["account_id"], "account"))
    category = query.get("category_id")
    if category == "none":
        where.append("t.category_id IS NULL AND t.transfer_group IS NULL")
    elif category == "transfer":
        where.append("t.transfer_group IS NOT NULL")
    elif category:
        where.append("t.category_id = ?")
        params.append(v.ident(category, "category"))
    if query.get("from"):
        where.append("t.date >= ?")
        params.append(v.iso_date(query["from"], "from"))
    if query.get("to"):
        where.append("t.date <= ?")
        params.append(v.iso_date(query["to"], "to"))
    if query.get("search"):
        where.append("(t.payee LIKE ? OR t.note LIKE ?)")
        term = f"%{str(query['search']).strip()}%"
        params += [term, term]
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    limit = min(int(query.get("limit") or 100), 500)
    offset = max(int(query.get("offset") or 0), 0)
    total, income, expenses = conn.execute(
        f"""SELECT COUNT(*), COALESCE(SUM(CASE WHEN t.amount > 0 THEN t.amount END), 0),
                   COALESCE(SUM(CASE WHEN t.amount < 0 THEN t.amount END), 0)
            FROM transactions t{clause}""",
        params,
    ).fetchone()
    items = rows(
        conn.execute(
            f"{TRANSACTION_SELECT}{clause} ORDER BY t.date DESC, t.id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
    )
    return {"items": items, "total": total, "income": income, "expenses": expenses}


def _check_category(conn: sqlite3.Connection, category_id: int | None, amount: int) -> None:
    if category_id is None:
        return
    kind = one(conn, "SELECT kind FROM categories WHERE id = ?", (category_id,))["kind"]
    # Positive amounts in an expense category are refunds and are allowed:
    # they reduce that category's spending.
    if kind == "income" and amount < 0:
        raise Invalid("An income category cannot be used for money going out")


def save_transaction(conn: sqlite3.Connection, data: dict) -> dict:
    account_id = v.ident(data.get("account_id"), "account")
    tx_date = v.iso_date(data.get("date"))
    amount = v.cents(data.get("amount"), "amount")
    if amount == 0:
        raise Invalid("Amount cannot be zero")
    payee = v.text(data, "payee", max_length=120)
    note = v.text(data, "note", required=False, max_length=500)
    category_id = v.optional_ident(data.get("category_id"), "category")
    one(conn, "SELECT id FROM accounts WHERE id = ?", (account_id,))
    _check_category(conn, category_id, amount)
    with conn:
        conn.execute("BEGIN")
        if data.get("id"):
            tx_id = v.ident(data["id"])
            existing = one(conn, "SELECT transfer_group FROM transactions WHERE id = ?", (tx_id,))
            if existing["transfer_group"]:
                raise Invalid("Transfers cannot be edited: delete it and record it again")
            conn.execute(
                """UPDATE transactions SET account_id = ?, date = ?, amount = ?, payee = ?, category_id = ?, note = ?
                   WHERE id = ?""",
                (account_id, tx_date, amount, payee, category_id, note, tx_id),
            )
        else:
            tx_id = conn.execute(
                """INSERT INTO transactions (account_id, date, amount, payee, category_id, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (account_id, tx_date, amount, payee, category_id, note, now()),
            ).lastrowid
    return one(conn, f"{TRANSACTION_SELECT} WHERE t.id = ?", (tx_id,))


def save_transfer(conn: sqlite3.Connection, data: dict) -> str:
    from_id = v.ident(data.get("from_account_id"), "from_account")
    to_id = v.ident(data.get("to_account_id"), "to_account")
    if from_id == to_id:
        raise Invalid("Choose two different accounts")
    amount = v.cents(data.get("amount"), "amount", minimum=1)
    tx_date = v.iso_date(data.get("date"))
    note = v.text(data, "note", required=False, max_length=500)
    source = one(conn, "SELECT name FROM accounts WHERE id = ?", (from_id,))["name"]
    target = one(conn, "SELECT name FROM accounts WHERE id = ?", (to_id,))["name"]
    group = uuid.uuid4().hex
    with conn:
        conn.execute("BEGIN")
        conn.executemany(
            """INSERT INTO transactions (account_id, date, amount, payee, note, transfer_group, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (from_id, tx_date, -amount, f"Transfer to {target}", note, group, now()),
                (to_id, tx_date, amount, f"Transfer from {source}", note, group, now()),
            ],
        )
    return group


def delete_transaction(conn: sqlite3.Connection, tx_id: int) -> None:
    tx = one(conn, "SELECT transfer_group FROM transactions WHERE id = ?", (v.ident(tx_id),))
    with conn:
        conn.execute("BEGIN")
        if tx["transfer_group"]:
            conn.execute("DELETE FROM transactions WHERE transfer_group = ?", (tx["transfer_group"],))
        else:
            conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))


# Assets, prices, trades, dividends


def list_assets(conn: sqlite3.Connection) -> list[dict]:
    return rows(
        conn.execute(
            """SELECT a.*, p.price AS last_price, p.date AS last_price_date,
                      (SELECT COUNT(*) FROM trades t WHERE t.asset_id = a.id) AS trades
               FROM assets a
               LEFT JOIN prices p ON p.asset_id = a.id
                    AND p.date = (SELECT MAX(date) FROM prices WHERE asset_id = a.id)
               ORDER BY a.symbol"""
        )
    )


def save_asset(conn: sqlite3.Connection, data: dict) -> dict:
    symbol = v.text(data, "symbol", max_length=20).upper()
    name = v.text(data, "name", max_length=120)
    kind = v.choice(data.get("kind"), "kind", ASSET_KINDS)
    region = v.choice(data.get("region"), "region", REGIONS)
    source = v.choice(data.get("price_source", "manual"), "price_source", PRICE_SOURCES)
    source_id = v.text(data, "source_id", required=False, max_length=80)
    if source == "coingecko" and not source_id:
        raise Invalid("CoinGecko needs the coin id, for example 'bitcoin'")
    try:
        with conn:
            conn.execute("BEGIN")
            if data.get("id"):
                asset_id = v.ident(data["id"])
                one(conn, "SELECT id FROM assets WHERE id = ?", (asset_id,))
                conn.execute(
                    """UPDATE assets SET symbol = ?, name = ?, kind = ?, region = ?, price_source = ?, source_id = ?
                       WHERE id = ?""",
                    (symbol, name, kind, region, source, source_id, asset_id),
                )
            else:
                asset_id = conn.execute(
                    """INSERT INTO assets (symbol, name, kind, region, price_source, source_id)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (symbol, name, kind, region, source, source_id),
                ).lastrowid
    except sqlite3.IntegrityError as exc:
        raise Invalid(f"An asset with symbol {symbol} already exists") from exc
    return next(a for a in list_assets(conn) if a["id"] == asset_id)


def delete_asset(conn: sqlite3.Connection, asset_id: int) -> None:
    asset_id = v.ident(asset_id)
    used = conn.execute(
        "SELECT (SELECT COUNT(*) FROM trades WHERE asset_id = ?) + (SELECT COUNT(*) FROM dividends WHERE asset_id = ?)",
        (asset_id, asset_id),
    ).fetchone()[0]
    if used:
        raise Invalid("This asset has trades or dividends: delete those first")
    with conn:
        conn.execute("BEGIN")
        if conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,)).rowcount == 0:
            raise NotFound()


def set_price(conn: sqlite3.Connection, data: dict, source: str = "manual") -> None:
    asset_id = v.ident(data.get("asset_id"), "asset")
    price_date = v.iso_date(data.get("date") or date.today().isoformat())
    price = v.positive_number(data.get("price"), "price", allow_zero=True)
    one(conn, "SELECT id FROM assets WHERE id = ?", (asset_id,))
    with conn:
        conn.execute("BEGIN")
        conn.execute(
            "INSERT OR REPLACE INTO prices (asset_id, date, price, source) VALUES (?, ?, ?, ?)",
            (asset_id, price_date, price, source),
        )


def list_prices(conn: sqlite3.Connection, asset_id: int) -> list[dict]:
    return rows(
        conn.execute(
            "SELECT date, price, source FROM prices WHERE asset_id = ? ORDER BY date DESC LIMIT 400",
            (v.ident(asset_id),),
        )
    )


TRADE_SELECT = """
    SELECT t.*, a.symbol, a.name AS asset_name, ac.name AS account_name
    FROM trades t JOIN assets a ON a.id = t.asset_id JOIN accounts ac ON ac.id = t.account_id
"""


def list_trades(conn: sqlite3.Connection, asset_id: int | None = None) -> list[dict]:
    if asset_id:
        return rows(conn.execute(f"{TRADE_SELECT} WHERE t.asset_id = ? ORDER BY t.date DESC, t.id DESC", (asset_id,)))
    return rows(conn.execute(f"{TRADE_SELECT} ORDER BY t.date DESC, t.id DESC"))


def check_holdings_never_negative(conn: sqlite3.Connection, asset_id: int) -> None:
    """Selling more than you own at that date is almost always a typo, and it
    would make every later figure wrong."""
    held = 0.0
    for trade in conn.execute(
        "SELECT date, side, quantity FROM trades WHERE asset_id = ? ORDER BY date, side = 'sell', id", (asset_id,)
    ):
        held += trade["quantity"] if trade["side"] == "buy" else -trade["quantity"]
        if held < -1e-9:
            raise Invalid(f"On {trade['date']} this would sell more units than you hold")


def save_trade(conn: sqlite3.Connection, data: dict) -> dict:
    account_id = v.ident(data.get("account_id"), "account")
    asset_id = v.ident(data.get("asset_id"), "asset")
    trade_date = v.iso_date(data.get("date"))
    side = v.choice(data.get("side"), "side", ("buy", "sell"))
    quantity = v.positive_number(data.get("quantity"), "quantity")
    price = v.positive_number(data.get("price"), "price", allow_zero=True)
    fees = v.cents(data.get("fees", 0), "fees", minimum=0)
    note = v.text(data, "note", required=False, max_length=500)
    one(conn, "SELECT id FROM accounts WHERE id = ?", (account_id,))
    one(conn, "SELECT id FROM assets WHERE id = ?", (asset_id,))
    with conn:
        conn.execute("BEGIN")
        if data.get("id"):
            trade_id = v.ident(data["id"])
            old = one(conn, "SELECT asset_id FROM trades WHERE id = ?", (trade_id,))
            conn.execute(
                """UPDATE trades SET account_id = ?, asset_id = ?, date = ?, side = ?, quantity = ?, price = ?,
                   fees = ?, note = ? WHERE id = ?""",
                (account_id, asset_id, trade_date, side, quantity, price, fees, note, trade_id),
            )
            if old["asset_id"] != asset_id:
                check_holdings_never_negative(conn, old["asset_id"])
        else:
            trade_id = conn.execute(
                """INSERT INTO trades (account_id, asset_id, date, side, quantity, price, fees, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (account_id, asset_id, trade_date, side, quantity, price, fees, note, now()),
            ).lastrowid
        check_holdings_never_negative(conn, asset_id)
        # A trade is also a price observation; keep it unless a better one exists.
        conn.execute(
            "INSERT OR IGNORE INTO prices (asset_id, date, price, source) VALUES (?, ?, ?, 'trade')",
            (asset_id, trade_date, price),
        )
    return one(conn, f"{TRADE_SELECT} WHERE t.id = ?", (trade_id,))


def delete_trade(conn: sqlite3.Connection, trade_id: int) -> None:
    trade = one(conn, "SELECT asset_id FROM trades WHERE id = ?", (v.ident(trade_id),))
    with conn:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
        check_holdings_never_negative(conn, trade["asset_id"])


DIVIDEND_SELECT = """
    SELECT d.*, a.symbol, a.name AS asset_name, ac.name AS account_name
    FROM dividends d JOIN assets a ON a.id = d.asset_id JOIN accounts ac ON ac.id = d.account_id
"""


def list_dividends(conn: sqlite3.Connection) -> list[dict]:
    return rows(conn.execute(f"{DIVIDEND_SELECT} ORDER BY d.date DESC, d.id DESC"))


def save_dividend(conn: sqlite3.Connection, data: dict) -> dict:
    account_id = v.ident(data.get("account_id"), "account")
    asset_id = v.ident(data.get("asset_id"), "asset")
    div_date = v.iso_date(data.get("date"))
    amount = v.cents(data.get("amount"), "amount", minimum=1)
    tax = v.cents(data.get("tax", 0), "tax", minimum=0)
    if tax > amount:
        raise Invalid("Tax cannot be higher than the gross amount")
    note = v.text(data, "note", required=False, max_length=500)
    one(conn, "SELECT id FROM accounts WHERE id = ?", (account_id,))
    one(conn, "SELECT id FROM assets WHERE id = ?", (asset_id,))
    with conn:
        conn.execute("BEGIN")
        if data.get("id"):
            div_id = v.ident(data["id"])
            if conn.execute(
                """UPDATE dividends SET account_id = ?, asset_id = ?, date = ?, amount = ?, tax = ?, note = ?
                   WHERE id = ?""",
                (account_id, asset_id, div_date, amount, tax, note, div_id),
            ).rowcount == 0:
                raise NotFound()
        else:
            div_id = conn.execute(
                """INSERT INTO dividends (account_id, asset_id, date, amount, tax, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (account_id, asset_id, div_date, amount, tax, note, now()),
            ).lastrowid
    return one(conn, f"{DIVIDEND_SELECT} WHERE d.id = ?", (div_id,))


def delete_dividend(conn: sqlite3.Connection, div_id: int) -> None:
    with conn:
        conn.execute("BEGIN")
        if conn.execute("DELETE FROM dividends WHERE id = ?", (v.ident(div_id),)).rowcount == 0:
            raise NotFound()
