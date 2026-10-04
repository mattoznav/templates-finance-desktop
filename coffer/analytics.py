"""Figures for the dashboards. Money is returned in integer cents.

Holdings use the average cost method: a sale removes cost basis in proportion
to the units sold, and the difference is the realized gain.
"""

from __future__ import annotations

import bisect
import calendar
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import store
from . import validate as v

# What counts as income and spending. Transfers move money between your own
# accounts, so they are neither. Positive amounts in an expense category are
# refunds and reduce that category's spending.
INCOME_SQL = """
    SELECT COALESCE(SUM(t.amount), 0) FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
    WHERE t.transfer_group IS NULL AND t.amount > 0 AND (c.kind = 'income' OR c.id IS NULL)
      AND t.date BETWEEN ? AND ?
"""
EXPENSES_SQL = """
    SELECT COALESCE(-SUM(t.amount), 0) FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
    WHERE t.transfer_group IS NULL AND (c.kind = 'expense' OR (c.id IS NULL AND t.amount < 0))
      AND t.date BETWEEN ? AND ?
"""
DIVIDENDS_SQL = "SELECT COALESCE(SUM(amount - tax), 0) FROM dividends WHERE date BETWEEN ? AND ?"


def month_bounds(month: str) -> tuple[str, str]:
    year, mon = int(month[:4]), int(month[5:7])
    last = calendar.monthrange(year, mon)[1]
    return f"{month}-01", f"{month}-{last:02d}"


def shift_month(month: str, delta: int) -> str:
    index = int(month[:4]) * 12 + int(month[5:7]) - 1 + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def current_month() -> str:
    return date.today().isoformat()[:7]


# Holdings


@dataclass
class Position:
    quantity: float = 0.0
    cost: float = 0.0  # remaining cost basis, in cents
    realized: float = 0.0  # in cents
    invested: float = 0.0  # every euro ever put in, in cents

    def apply(self, side: str, quantity: float, price: float, fees: int) -> None:
        value = quantity * price * 100
        if side == "buy":
            self.quantity += quantity
            self.cost += value + fees
            self.invested += value + fees
            return
        fraction = min(quantity / self.quantity, 1.0) if self.quantity > 0 else 1.0
        basis = self.cost * fraction
        self.realized += value - fees - basis
        self.cost -= basis
        self.quantity -= quantity
        if self.quantity < 1e-9:
            self.quantity, self.cost = 0.0, 0.0


@dataclass
class PriceBook:
    dates: dict[int, list[str]] = field(default_factory=dict)
    values: dict[int, list[float]] = field(default_factory=dict)

    @classmethod
    def load(cls, conn: sqlite3.Connection) -> "PriceBook":
        book = cls()
        for row in conn.execute("SELECT asset_id, date, price FROM prices ORDER BY asset_id, date"):
            book.dates.setdefault(row["asset_id"], []).append(row["date"])
            book.values.setdefault(row["asset_id"], []).append(row["price"])
        return book

    def on(self, asset_id: int, day: str) -> float | None:
        """The last known price on or before ``day``."""
        dates = self.dates.get(asset_id)
        if not dates:
            return None
        index = bisect.bisect_right(dates, day) - 1
        return self.values[asset_id][index] if index >= 0 else None

    def latest(self, asset_id: int) -> tuple[float | None, str | None]:
        dates = self.dates.get(asset_id)
        return (self.values[asset_id][-1], dates[-1]) if dates else (None, None)


def _trades(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    # Buys before sells on the same day, so a same-day round trip never dips below zero.
    return conn.execute(
        "SELECT asset_id, date, side, quantity, price, fees FROM trades ORDER BY date, side = 'sell', id"
    ).fetchall()


def portfolio(conn: sqlite3.Connection) -> dict:
    assets = {a["id"]: a for a in store.list_assets(conn)}
    book = PriceBook.load(conn)
    positions: dict[int, Position] = defaultdict(Position)
    for t in _trades(conn):
        positions[t["asset_id"]].apply(t["side"], t["quantity"], t["price"], t["fees"])

    dividends = defaultdict(int)
    for row in conn.execute("SELECT asset_id, SUM(amount - tax) AS net FROM dividends GROUP BY asset_id"):
        dividends[row["asset_id"]] = row["net"]

    holdings = []
    for asset_id, position in positions.items():
        asset = assets[asset_id]
        price, price_date = book.latest(asset_id)
        value = position.quantity * (price or 0) * 100
        holdings.append(
            {
                "asset_id": asset_id,
                "symbol": asset["symbol"],
                "name": asset["name"],
                "kind": asset["kind"],
                "region": asset["region"],
                "quantity": position.quantity,
                "average_cost": (position.cost / position.quantity / 100) if position.quantity else 0,
                "price": price,
                "price_date": price_date,
                "value": round(value),
                "cost": round(position.cost),
                "unrealized": round(value - position.cost),
                "unrealized_pct": ((value - position.cost) / position.cost) if position.cost else 0,
                "realized": round(position.realized),
                "dividends": dividends.get(asset_id, 0),
                "open": position.quantity > 0,
            }
        )
    holdings.sort(key=lambda h: (not h["open"], -h["value"]))
    open_holdings = [h for h in holdings if h["open"]]
    total_value = sum(h["value"] for h in open_holdings)
    for h in holdings:
        h["weight"] = h["value"] / total_value if total_value and h["open"] else 0

    def allocation(key: str) -> list[dict]:
        groups: dict[str, int] = defaultdict(int)
        for h in open_holdings:
            groups[h[key]] += h["value"]
        return sorted(
            ({"key": k, "value": val, "weight": val / total_value if total_value else 0} for k, val in groups.items()),
            key=lambda g: -g["value"],
        )

    total_cost = sum(h["cost"] for h in open_holdings)
    realized = sum(h["realized"] for h in holdings)
    dividends_total = sum(dividends.values())
    stale = [h["symbol"] for h in open_holdings if h["price_date"] and h["price_date"] < (date.today() - timedelta(days=7)).isoformat()]
    return {
        "holdings": holdings,
        "allocation": {"kind": allocation("kind"), "region": allocation("region")},
        "totals": {
            "value": total_value,
            "cost": total_cost,
            "unrealized": total_value - total_cost,
            "unrealized_pct": (total_value - total_cost) / total_cost if total_cost else 0,
            "realized": realized,
            "dividends": dividends_total,
            "total_return": total_value - total_cost + realized + dividends_total,
        },
        "stale_prices": stale,
    }


# Net worth over time


def _month_ends(first: date, last: date) -> list[date]:
    points = []
    year, month = first.year, first.month
    while True:
        end = date(year, month, calendar.monthrange(year, month)[1])
        if end >= last:
            points.append(last)
            return points
        points.append(end)
        month += 1
        if month == 13:
            year, month = year + 1, 1


def net_worth_series(conn: sqlite3.Connection, months: int | None = None) -> list[dict]:
    today = date.today()
    firsts = [
        conn.execute("SELECT MIN(opening_date) FROM accounts").fetchone()[0],
        conn.execute("SELECT MIN(date) FROM cash_flows").fetchone()[0],
    ]
    firsts = [d for d in firsts if d]
    if not firsts:
        return []
    first = min(date.fromisoformat(d) for d in firsts)
    if first > today:
        first = today
    points = _month_ends(first, today)
    if months:
        points = points[-months:]

    openings = sorted((row["opening_date"], row["opening_balance"]) for row in conn.execute("SELECT * FROM accounts"))
    flows = conn.execute("SELECT date, amount FROM cash_flows ORDER BY date").fetchall()
    trades = _trades(conn)
    book = PriceBook.load(conn)

    series = []
    cash = 0
    oi = fi = ti = 0
    positions: dict[int, Position] = defaultdict(Position)
    # Everything before the first point is folded into the starting state.
    for point in points:
        day = point.isoformat()
        while oi < len(openings) and openings[oi][0] <= day:
            cash += openings[oi][1]
            oi += 1
        while fi < len(flows) and flows[fi]["date"] <= day:
            cash += flows[fi]["amount"]
            fi += 1
        while ti < len(trades) and trades[ti]["date"] <= day:
            t = trades[ti]
            positions[t["asset_id"]].apply(t["side"], t["quantity"], t["price"], t["fees"])
            ti += 1
        investments = 0.0
        cost = 0.0
        for asset_id, position in positions.items():
            if position.quantity <= 0:
                continue
            price = book.on(asset_id, day)
            investments += position.quantity * (price or 0) * 100
            cost += position.cost
        series.append(
            {
                "date": day,
                "cash": cash,
                "investments": round(investments),
                "cost_basis": round(cost),
                "net_worth": cash + round(investments),
            }
        )
    return series


# Income and spending


def cash_flow(conn: sqlite3.Connection, months: int = 12) -> list[dict]:
    end = current_month()
    result = []
    for offset in range(months - 1, -1, -1):
        month = shift_month(end, -offset)
        start, stop = month_bounds(month)
        income = conn.execute(INCOME_SQL, (start, stop)).fetchone()[0] + conn.execute(DIVIDENDS_SQL, (start, stop)).fetchone()[0]
        expenses = conn.execute(EXPENSES_SQL, (start, stop)).fetchone()[0]
        result.append({"month": month, "income": income, "expenses": expenses, "net": income - expenses})
    return result


def spending_by_category(conn: sqlite3.Connection, start: str, stop: str) -> list[dict]:
    rows = store.rows(
        conn.execute(
            """SELECT c.id, COALESCE(c.name, 'Uncategorized') AS name, COALESCE(c.color, '#6b7075') AS color,
                      -SUM(t.amount) AS spent
               FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
               WHERE t.transfer_group IS NULL AND t.date BETWEEN ? AND ?
                 AND (c.kind = 'expense' OR (c.id IS NULL AND t.amount < 0))
               GROUP BY c.id ORDER BY spent DESC""",
            (start, stop),
        )
    )
    return [r for r in rows if r["spent"] > 0]


def budget_report(conn: sqlite3.Connection, month: str) -> dict:
    month = v.month(month)
    start, stop = month_bounds(month)
    history_start = month_bounds(shift_month(month, -3))[0]
    history_stop = month_bounds(shift_month(month, -1))[1]
    lines = []
    for category in conn.execute("SELECT * FROM categories WHERE kind = 'expense' ORDER BY name"):
        spent = conn.execute(
            """SELECT COALESCE(-SUM(amount), 0) FROM transactions
               WHERE category_id = ? AND transfer_group IS NULL AND date BETWEEN ? AND ?""",
            (category["id"], start, stop),
        ).fetchone()[0]
        previous = conn.execute(
            """SELECT COALESCE(-SUM(amount), 0) FROM transactions
               WHERE category_id = ? AND transfer_group IS NULL AND date BETWEEN ? AND ?""",
            (category["id"], history_start, history_stop),
        ).fetchone()[0]
        budget = category["monthly_budget"]
        lines.append(
            {
                "category_id": category["id"],
                "name": category["name"],
                "color": category["color"],
                "budget": budget,
                "spent": spent,
                "remaining": (budget - spent) if budget is not None else None,
                "used": (spent / budget) if budget else None,
                "average_3m": round(previous / 3),
            }
        )
    uncategorized = conn.execute(
        """SELECT COALESCE(-SUM(amount), 0) FROM transactions
           WHERE category_id IS NULL AND transfer_group IS NULL AND amount < 0 AND date BETWEEN ? AND ?""",
        (start, stop),
    ).fetchone()[0]
    lines.sort(key=lambda line: (line["budget"] is None, -(line["used"] or 0), -line["spent"]))
    budgeted = [line for line in lines if line["budget"] is not None]
    income = conn.execute(INCOME_SQL, (start, stop)).fetchone()[0] + conn.execute(DIVIDENDS_SQL, (start, stop)).fetchone()[0]
    expenses = conn.execute(EXPENSES_SQL, (start, stop)).fetchone()[0]
    return {
        "month": month,
        "lines": lines,
        "uncategorized": uncategorized,
        "totals": {
            "budget": sum(line["budget"] for line in budgeted),
            "spent_in_budgets": sum(line["spent"] for line in budgeted),
            "income": income,
            "expenses": expenses,
            "saved": income - expenses,
            "savings_rate": (income - expenses) / income if income else None,
        },
        # Days elapsed, to compare spending pace with the share of the month gone.
        "progress": _month_progress(month),
    }


def _month_progress(month: str) -> float:
    today = date.today()
    if month < today.isoformat()[:7]:
        return 1.0
    if month > today.isoformat()[:7]:
        return 0.0
    return today.day / calendar.monthrange(today.year, today.month)[1]


def dividends_summary(conn: sqlite3.Connection) -> dict:
    by_year = store.rows(
        conn.execute(
            """SELECT substr(date, 1, 4) AS year, SUM(amount) AS gross, SUM(tax) AS tax, SUM(amount - tax) AS net
               FROM dividends GROUP BY year ORDER BY year"""
        )
    )
    year_ago = (date.today() - timedelta(days=365)).isoformat()
    trailing = conn.execute("SELECT COALESCE(SUM(amount - tax), 0) FROM dividends WHERE date > ?", (year_ago,)).fetchone()[0]
    return {"by_year": by_year, "trailing_12m": trailing, "items": store.list_dividends(conn)[:50]}


def overview(conn: sqlite3.Connection) -> dict:
    month = current_month()
    start, stop = month_bounds(month)
    series = net_worth_series(conn)
    latest = series[-1] if series else {"net_worth": 0, "cash": 0, "investments": 0, "cost_basis": 0}
    previous_end = month_bounds(shift_month(month, -1))[1]
    previous = next((p for p in reversed(series) if p["date"] <= previous_end), None)
    income = conn.execute(INCOME_SQL, (start, stop)).fetchone()[0] + conn.execute(DIVIDENDS_SQL, (start, stop)).fetchone()[0]
    expenses = conn.execute(EXPENSES_SQL, (start, stop)).fetchone()[0]
    budgets = [line for line in budget_report(conn, month)["lines"] if line["budget"]]
    recent = store.list_transactions(conn, {"limit": 8})["items"]
    return {
        "month": month,
        "net_worth": latest["net_worth"],
        "cash": latest["cash"],
        "investments": latest["investments"],
        "change_this_month": latest["net_worth"] - previous["net_worth"] if previous else None,
        "income": income,
        "expenses": expenses,
        "savings_rate": (income - expenses) / income if income else None,
        "series": series[-24:],
        "spending": spending_by_category(conn, start, stop),
        "budgets": budgets[:5],
        "recent": recent,
        "accounts": store.list_accounts(conn, include_archived=False),
        "progress": _month_progress(month),
    }
