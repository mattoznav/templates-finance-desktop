"""Demo data: two years of a fictional person's finances.

Every name here is invented. Instruments are fictional too, with simulated
prices, so the demo never looks like a statement about a real security.
"""

from __future__ import annotations

import calendar
import random
import sqlite3
import uuid
from datetime import date, timedelta

from . import store
from .validate import to_cents

SEED = 20261004
# Prices get their own generator, so the market story does not change with
# the date the demo is generated on.
PRICE_SEED = 25
MONTHS = 26

ASSETS = [
    # symbol, name, kind, region, start price, monthly drift, monthly volatility
    ("GEQ", "Global Equity Index ETF", "etf", "global", 92.0, 0.007, 0.035),
    ("EUSC", "Europe Small Cap ETF", "etf", "europe", 41.0, 0.004, 0.045),
    ("EMKT", "Emerging Markets ETF", "etf", "emerging", 28.5, 0.003, 0.05),
    ("GBND", "Global Aggregate Bond ETF", "bond", "global", 51.0, 0.001, 0.012),
    ("AURA", "Aurelia Robotics", "stock", "north_america", 64.0, 0.012, 0.09),
    ("DAB", "Digital Asset Basket", "crypto", "other", 180.0, 0.015, 0.16),
]

RULES = [
    ("Greenmarket", "Groceries"),
    ("Corner Grocer", "Groceries"),
    ("Fresh & Co", "Groceries"),
    ("Trattoria", "Eating out"),
    ("Noodle Bar", "Eating out"),
    ("Cafe Linden", "Eating out"),
    ("Metro", "Transport"),
    ("Fuel", "Transport"),
    ("StreamBox", "Subscriptions"),
    ("Music+", "Subscriptions"),
    ("Elm Court", "Housing"),
    ("City Power", "Utilities"),
    ("Lumen Fibre", "Utilities"),
    ("Fieldstone Studio", "Salary"),
]

BUDGETS = {
    "Housing": 1050_00,
    "Utilities": 170_00,
    "Groceries": 380_00,
    "Eating out": 180_00,
    "Transport": 90_00,
    "Shopping": 150_00,
    "Leisure": 120_00,
    "Subscriptions": 75_00,
}


def populate(conn: sqlite3.Connection, today: date | None = None) -> None:
    rng = random.Random(SEED)
    today = today or date.today()
    start = _add_months(date(today.year, today.month, 1), -MONTHS)
    stamp = store.now()
    cat = {row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM categories")}

    with conn:
        conn.execute("BEGIN")
        for name, budget in BUDGETS.items():
            conn.execute("UPDATE categories SET monthly_budget = ? WHERE id = ?", (budget, cat[name]))
        for pattern, category in RULES:
            conn.execute("INSERT INTO rules (pattern, category_id) VALUES (?, ?)", (pattern, cat[category]))

        def account(name: str, kind: str, institution: str, opening: int) -> int:
            return conn.execute(
                """INSERT INTO accounts (name, kind, institution, opening_balance, opening_date, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, kind, institution, opening, start.isoformat(), stamp),
            ).lastrowid

        checking = account("Everyday", "checking", "Harbor Bank", 2_430_00)
        savings = account("Rainy day fund", "savings", "Harbor Bank", 7_800_00)
        card = account("Travel card", "credit_card", "Harbor Bank", 0)
        broker = account("Investments", "brokerage", "Meridian Brokerage", 0)

        def tx(account_id: int, day: date, amount: int, payee: str, category: str | None, note: str = "") -> None:
            if day > today:
                return
            conn.execute(
                """INSERT INTO transactions (account_id, date, amount, payee, category_id, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (account_id, day.isoformat(), amount, payee, cat[category] if category else None, note, stamp),
            )

        def transfer(source: int, target: int, day: date, amount: int, label_from: str, label_to: str) -> None:
            if day > today:
                return
            group = uuid.uuid4().hex
            conn.executemany(
                """INSERT INTO transactions (account_id, date, amount, payee, transfer_group, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (source, day.isoformat(), -amount, f"Transfer to {label_to}", group, stamp),
                    (target, day.isoformat(), amount, f"Transfer from {label_from}", group, stamp),
                ],
            )

        def money(low: float, high: float) -> int:
            return to_cents(rng.uniform(low, high))

        for offset in range(MONTHS + 1):
            first = _add_months(start, offset)
            days = calendar.monthrange(first.year, first.month)[1]

            def day(n: int) -> date:
                return first.replace(day=min(n, days))

            raise_factor = 1.0 if offset < 14 else 1.06
            tx(checking, day(27), to_cents(3_180 * raise_factor), "Fieldstone Studio payroll", "Salary")
            if first.month == 12:
                tx(checking, day(15), 1_420_00, "Fieldstone Studio bonus", "Salary")
            tx(checking, day(2), -1_050_00, "Elm Court Lettings rent", "Housing")
            tx(checking, day(5), -money(62, 148), "City Power & Water", "Utilities")
            tx(checking, day(8), -29_90, "Lumen Fibre broadband", "Utilities")
            tx(checking, day(3), -39_00, "Metro monthly pass", "Transport")
            tx(checking, day(11), -12_99, "StreamBox", "Subscriptions")
            tx(checking, day(14), -10_99, "Music+ family", "Subscriptions")
            tx(checking, day(6), -45_00, "Gym Plus membership", "Leisure")

            for _ in range(rng.randint(8, 12)):
                shop = rng.choice(["Greenmarket", "Corner Grocer", "Fresh & Co"])
                tx(checking, day(rng.randint(1, days)), -money(14, 96), shop, "Groceries")
            for _ in range(rng.randint(3, 7)):
                place = rng.choice(["Trattoria Sole", "Noodle Bar Kai", "Cafe Linden", "Burger Yard"])
                tx(checking, day(rng.randint(1, days)), -money(9, 58), place, "Eating out")
            if rng.random() < 0.5:
                tx(checking, day(rng.randint(1, days)), -money(40, 70), "Fuel stop", "Transport")
            if rng.random() < 0.35:
                tx(checking, day(rng.randint(1, days)), -money(8, 45), "Linden Pharmacy", "Health")
            if rng.random() < 0.6:
                tx(card, day(rng.randint(1, days)), -money(25, 190), rng.choice(["Atlas Outfitters", "Pagebound Books", "Homeware Loft"]), "Shopping")
            if rng.random() < 0.5:
                tx(card, day(rng.randint(1, days)), -money(15, 80), rng.choice(["Cinema Paradiso", "Concert Hall", "Climbing Wall"]), "Leisure")
            if first.month in (4, 8):
                tx(card, day(9), -money(320, 640), "Skyway Airlines", "Travel")
                tx(card, day(18), -money(380, 760), "Harbour View Hotel", "Travel")
            if first.month == 12:
                for _ in range(3):
                    tx(card, day(rng.randint(5, 22)), -money(25, 120), "Gift shop", "Gifts")
            if rng.random() < 0.15:
                tx(checking, day(rng.randint(1, days)), money(20, 140), "Marketplace sale", "Other income")
            if rng.random() < 0.2:
                tx(card, day(rng.randint(1, days)), money(15, 60), "Atlas Outfitters refund", "Shopping")
            tx(checking, day(28), -2_50, "Account fee", "Fees and taxes")

            # Card balance is paid off from checking the following month.
            prev_first = _add_months(first, -1)
            if offset > 0:
                owed = -conn.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE account_id = ? AND date BETWEEN ? AND ? AND transfer_group IS NULL",
                    (card, prev_first.isoformat(), (first - timedelta(days=1)).isoformat()),
                ).fetchone()[0]
                if owed > 0:
                    transfer(checking, card, day(4), owed, "Everyday", "Travel card")
            transfer(checking, savings, day(28), 250_00, "Everyday", "Rainy day fund")
            transfer(checking, broker, day(28), 560_00, "Everyday", "Investments")
            if offset % 3 == 2:
                tx(savings, day(days), money(8, 14), "Interest", "Other income")

        _investments(conn, random.Random(PRICE_SEED), broker, start, today, stamp)


def _investments(conn: sqlite3.Connection, rng: random.Random, broker: int, start: date, today: date, stamp: str) -> None:
    ids = {}
    paths: dict[str, list[tuple[date, float]]] = {}
    for symbol, name, kind, region, price, drift, vol in ASSETS:
        ids[symbol] = conn.execute(
            "INSERT INTO assets (symbol, name, kind, region, price_source) VALUES (?, ?, ?, ?, 'manual')",
            (symbol, name, kind, region),
        ).lastrowid
        # Weekly random walk; the weekly drift and volatility follow from the monthly ones.
        path = []
        day = start
        while day <= today:
            path.append((day, round(price, 4)))
            price *= 1 + rng.gauss(drift / 4.3, vol / 2.07)
            price = max(price, 0.5)
            day += timedelta(days=7)
        if path[-1][0] != today:
            path.append((today, round(price, 4)))
        paths[symbol] = path
        conn.executemany(
            "INSERT INTO prices (asset_id, date, price, source) VALUES (?, ?, ?, 'demo')",
            [(ids[symbol], d.isoformat(), p) for d, p in path],
        )

    def price_on(symbol: str, day: date) -> float:
        return [p for d, p in paths[symbol] if d <= day][-1]

    plan = {"GEQ": 0.5, "EUSC": 0.15, "EMKT": 0.15, "GBND": 0.2}
    held: dict[str, float] = {s: 0.0 for s in ids}
    for offset in range(MONTHS + 1):
        day = _add_months(start, offset).replace(day=1) + timedelta(days=29)
        day = min(day, today)
        if day > today or day <= start:
            continue
        for symbol, share in plan.items():
            price = price_on(symbol, day)
            quantity = round(500 * share / price, 3)
            if quantity <= 0:
                continue
            held[symbol] += quantity
            conn.execute(
                """INSERT INTO trades (account_id, asset_id, date, side, quantity, price, fees, created_at)
                   VALUES (?, ?, ?, 'buy', ?, ?, ?, ?)""",
                (broker, ids[symbol], day.isoformat(), quantity, price, 1_00 if symbol == "GEQ" else 0, stamp),
            )
        if offset in (3, 11, 19):
            symbol = "AURA" if offset != 11 else "DAB"
            price = price_on(symbol, day)
            quantity = round(300 / price, 3)
            held[symbol] += quantity
            conn.execute(
                """INSERT INTO trades (account_id, asset_id, date, side, quantity, price, fees, created_at)
                   VALUES (?, ?, ?, 'buy', ?, ?, 200, ?)""",
                (broker, ids[symbol], day.isoformat(), quantity, price, stamp),
            )
        if offset == 22 and held["AURA"] > 0:
            quantity = round(held["AURA"] / 2, 3)
            held["AURA"] -= quantity
            conn.execute(
                """INSERT INTO trades (account_id, asset_id, date, side, quantity, price, fees, note, created_at)
                   VALUES (?, ?, ?, 'sell', ?, ?, 200, 'Trimmed after a strong run', ?)""",
                (broker, ids["AURA"], day.isoformat(), quantity, price_on("AURA", day), stamp),
            )
        # Quarterly bond distribution and a half-yearly stock dividend.
        if offset % 3 == 1 and held["GBND"] > 0:
            gross = to_cents(held["GBND"] * price_on("GBND", day) * 0.007)
            if gross > 0:
                conn.execute(
                    """INSERT INTO dividends (account_id, asset_id, date, amount, tax, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (broker, ids["GBND"], (day - timedelta(days=12)).isoformat(), gross, round(gross * 0.26), stamp),
                )
        if offset % 6 == 5 and held["AURA"] > 0:
            gross = to_cents(held["AURA"] * 0.45)
            conn.execute(
                """INSERT INTO dividends (account_id, asset_id, date, amount, tax, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (broker, ids["AURA"], (day - timedelta(days=8)).isoformat(), gross, round(gross * 0.26), stamp),
            )


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))
