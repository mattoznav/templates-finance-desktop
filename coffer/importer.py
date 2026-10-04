"""CSV import (bank statements and broker trades) and CSV export.

Bank exports differ in delimiter, date format, decimal separator and whether
money in and out share a column, so the interface shows a preview and lets
the user map columns. Imports are idempotent: each row gets a hash, and a row
already imported into the same account is skipped.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sqlite3
from collections import Counter
from datetime import datetime

from . import store
from . import validate as v
from .errors import Invalid

MAX_IMPORT_BYTES = 10 * 1024 * 1024
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%y", "%Y/%m/%d", "%Y%m%d"]

HEADER_HINTS = {
    "date": ["date", "data", "booking", "valuta", "fecha", "datum"],
    "amount": ["amount", "importo", "betrag", "importe", "value"],
    "debit": ["debit", "dare", "uscite", "addebit", "withdrawal", "out"],
    "credit": ["credit", "avere", "entrate", "accredit", "deposit", "in"],
    "payee": ["description", "descrizione", "payee", "merchant", "causale", "details", "memo", "name"],
}


def _read(content: str, delimiter: str | None = None) -> tuple[list[list[str]], str]:
    if not isinstance(content, str) or not content.strip():
        raise Invalid("The file is empty")
    if len(content.encode()) > MAX_IMPORT_BYTES:
        raise Invalid("The file is larger than 10 MB")
    content = content.lstrip("﻿")
    if not delimiter:
        try:
            delimiter = csv.Sniffer().sniff(content[:4096], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    table = [row for row in csv.reader(io.StringIO(content), delimiter=delimiter) if any(cell.strip() for cell in row)]
    if not table:
        raise Invalid("No rows found")
    return table, delimiter


def parse_amount(text: str, decimal: str = "auto") -> int:
    """Turns '1.234,56', '-12.30', '(45.00)', '€ 7' or '12,5-' into cents."""
    raw = text.strip()
    if not raw:
        raise ValueError("empty amount")
    negative = raw.startswith("(") and raw.endswith(")") or raw.startswith("-") or raw.endswith("-")
    digits = re.sub(r"[^0-9.,]", "", raw)
    if not digits or not re.search(r"\d", digits):
        raise ValueError("no digits")
    if decimal == "auto":
        if "," in digits and "." in digits:
            decimal = "comma" if digits.rfind(",") > digits.rfind(".") else "dot"
        elif "," in digits:
            decimal = "comma" if re.search(r",\d{1,2}$", digits) else "dot"
        else:
            # A single dot is a decimal point; repeated dots in groups of three
            # ('1.234.567') are thousands separators.
            decimal = "comma" if digits.count(".") > 1 else "dot"
    if decimal == "comma":
        digits = digits.replace(".", "").replace(",", ".")
    else:
        digits = digits.replace(",", "")
    if digits.count(".") > 1:
        raise ValueError("ambiguous number")
    value = v.to_cents(float(digits))
    return -value if negative else value


def parse_date(text: str, fmt: str) -> str:
    return datetime.strptime(text.strip(), fmt).date().isoformat()


def _guess_date_format(values: list[str]) -> str | None:
    values = [x.strip() for x in values if x.strip()]
    for fmt in DATE_FORMATS:
        try:
            for value in values:
                datetime.strptime(value, fmt)
            return fmt
        except ValueError:
            continue
    return None


def _find(headers: list[str], key: str) -> int | None:
    lowered = [h.strip().lower() for h in headers]
    for hint in HEADER_HINTS[key]:
        for index, header in enumerate(lowered):
            if header == hint or (len(hint) > 2 and hint in header):
                return index
    return None


def inspect(content: str) -> dict:
    """Detects the layout of a CSV and proposes a column mapping."""
    table, delimiter = _read(content)
    headers = table[0]
    has_header = not any(re.fullmatch(r"[-+()€$£\s\d.,/]+", cell.strip() or "x") for cell in headers)
    body = table[1:] if has_header else table
    if not has_header:
        headers = [f"Column {i + 1}" for i in range(len(table[0]))]
    mapping = {
        "delimiter": delimiter,
        "has_header": has_header,
        "date_column": _find(headers, "date") if has_header else None,
        "date_format": None,
        "amount_mode": "single",
        "amount_column": _find(headers, "amount") if has_header else None,
        "debit_column": _find(headers, "debit") if has_header else None,
        "credit_column": _find(headers, "credit") if has_header else None,
        "payee_column": _find(headers, "payee") if has_header else None,
        "decimal": "auto",
        "invert": False,
    }
    if mapping["amount_column"] is None and mapping["debit_column"] is not None and mapping["credit_column"] is not None:
        mapping["amount_mode"] = "split"
    if mapping["date_column"] is None:
        for index in range(len(headers)):
            if _guess_date_format([row[index] for row in body[:20] if index < len(row)]):
                mapping["date_column"] = index
                break
    if mapping["date_column"] is not None:
        mapping["date_format"] = _guess_date_format(
            [row[mapping["date_column"]] for row in body[:50] if mapping["date_column"] < len(row)]
        )
    return {"headers": headers, "sample": body[:8], "rows": len(body), "mapping": mapping, "date_formats": DATE_FORMATS}


def _parse_rows(content: str, mapping: dict) -> list[dict]:
    table, _ = _read(content, mapping.get("delimiter"))
    body = table[1:] if mapping.get("has_header") else table
    date_col = mapping.get("date_column")
    payee_col = mapping.get("payee_column")
    fmt = mapping.get("date_format")
    decimal = mapping.get("decimal") or "auto"
    if date_col is None or payee_col is None or not fmt:
        raise Invalid("Choose the date column, its format and the description column")
    split = mapping.get("amount_mode") == "split"
    if split and (mapping.get("debit_column") is None or mapping.get("credit_column") is None):
        raise Invalid("Choose both the money out and money in columns")
    if not split and mapping.get("amount_column") is None:
        raise Invalid("Choose the amount column")

    def cell(row: list[str], index: int | None) -> str:
        return row[index] if index is not None and index < len(row) else ""

    parsed = []
    for number, row in enumerate(body, start=2 if mapping.get("has_header") else 1):
        item = {"line": number, "date": None, "amount": None, "payee": cell(row, payee_col).strip()[:120], "error": None}
        try:
            item["date"] = parse_date(cell(row, date_col), fmt)
        except ValueError:
            item["error"] = f"Unreadable date '{cell(row, date_col)}'"
        try:
            if split:
                out_text, in_text = cell(row, mapping["debit_column"]), cell(row, mapping["credit_column"])
                out_value = abs(parse_amount(out_text, decimal)) if out_text.strip() else 0
                in_value = abs(parse_amount(in_text, decimal)) if in_text.strip() else 0
                item["amount"] = in_value - out_value
            else:
                item["amount"] = parse_amount(cell(row, mapping["amount_column"]), decimal)
            if mapping.get("invert"):
                item["amount"] = -item["amount"]
            if item["amount"] == 0:
                item["error"] = item["error"] or "Amount is zero"
        except ValueError:
            item["error"] = item["error"] or "Unreadable amount"
        if not item["payee"] and not item["error"]:
            item["payee"] = "(no description)"
        parsed.append(item)

    # Two identical rows in one file (two coffees on the same day) are both
    # real: the occurrence number keeps their hashes apart.
    seen: Counter = Counter()
    for item in parsed:
        if item["error"]:
            continue
        key = f"{item['date']}|{item['amount']}|{item['payee'].lower()}"
        seen[key] += 1
        item["hash"] = hashlib.sha256(f"{key}|{seen[key]}".encode()).hexdigest()[:32]
    return parsed


def preview(conn: sqlite3.Connection, account_id: int, content: str, mapping: dict) -> dict:
    account_id = v.ident(account_id, "account")
    store.one(conn, "SELECT id FROM accounts WHERE id = ?", (account_id,))
    parsed = _parse_rows(content, mapping)
    existing = {
        row[0]
        for row in conn.execute("SELECT import_hash FROM transactions WHERE account_id = ? AND import_hash IS NOT NULL", (account_id,))
    }
    rules = store.list_rules(conn)
    kinds = {c["id"]: c["kind"] for c in store.list_categories(conn)}
    names = {c["id"]: c["name"] for c in store.list_categories(conn)}
    for item in parsed:
        if item["error"]:
            item["status"] = "error"
        elif item["hash"] in existing:
            item["status"] = "duplicate"
        else:
            item["status"] = "new"
            category_id = store.category_for(rules, item["payee"], item["amount"], kinds)
            item["category"] = names.get(category_id) if category_id else None
    counts = Counter(item["status"] for item in parsed)
    return {"rows": parsed[:500], "new": counts["new"], "duplicate": counts["duplicate"], "error": counts["error"]}


def commit(conn: sqlite3.Connection, account_id: int, content: str, mapping: dict) -> dict:
    account_id = v.ident(account_id, "account")
    store.one(conn, "SELECT id FROM accounts WHERE id = ?", (account_id,))
    parsed = _parse_rows(content, mapping)
    rules = store.list_rules(conn)
    kinds = {c["id"]: c["kind"] for c in store.list_categories(conn)}
    imported = duplicates = errors = 0
    stamp = store.now()
    with conn:
        conn.execute("BEGIN")
        for item in parsed:
            if item["error"]:
                errors += 1
                continue
            category_id = store.category_for(rules, item["payee"], item["amount"], kinds)
            cursor = conn.execute(
                """INSERT OR IGNORE INTO transactions (account_id, date, amount, payee, category_id, import_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (account_id, item["date"], item["amount"], item["payee"], category_id, item["hash"], stamp),
            )
            if cursor.rowcount:
                imported += 1
            else:
                duplicates += 1
    return {"imported": imported, "duplicates": duplicates, "errors": errors}


TRADE_COLUMNS = ["date", "symbol", "side", "quantity", "price", "fees"]


def import_trades(conn: sqlite3.Connection, account_id: int, content: str) -> dict:
    """Broker exports vary too much to guess; this reads a documented layout:
    date (YYYY-MM-DD), symbol, side (buy/sell), quantity, price, fees."""
    account_id = v.ident(account_id, "account")
    store.one(conn, "SELECT id FROM accounts WHERE id = ?", (account_id,))
    table, _ = _read(content)
    header = [h.strip().lower() for h in table[0]]
    if header[: len(TRADE_COLUMNS)] != TRADE_COLUMNS:
        raise Invalid("The first row must be: " + ",".join(TRADE_COLUMNS))
    assets = {a["symbol"]: a["id"] for a in store.list_assets(conn)}
    imported = duplicates = created = 0
    problems: list[str] = []
    seen: Counter = Counter()
    touched: set[int] = set()
    with conn:
        conn.execute("BEGIN")
        for line, row in enumerate(table[1:], start=2):
            try:
                trade_date = parse_date(row[0], "%Y-%m-%d")
                symbol = row[1].strip().upper()
                side = row[2].strip().lower()
                if not symbol or side not in ("buy", "sell"):
                    raise ValueError
                quantity = float(row[3])
                price = float(row[4])
                fees = abs(parse_amount(row[5])) if len(row) > 5 and row[5].strip() else 0
                if quantity <= 0 or price < 0:
                    raise ValueError
            except (ValueError, IndexError):
                problems.append(f"Line {line}: unreadable row")
                continue
            if symbol not in assets:
                assets[symbol] = conn.execute(
                    "INSERT INTO assets (symbol, name, kind, region, price_source) VALUES (?, ?, 'other', 'other', 'manual')",
                    (symbol, symbol),
                ).lastrowid
                created += 1
            key = f"{trade_date}|{symbol}|{side}|{quantity}|{price}|{fees}"
            seen[key] += 1
            digest = hashlib.sha256(f"{key}|{seen[key]}".encode()).hexdigest()[:32]
            cursor = conn.execute(
                """INSERT OR IGNORE INTO trades (account_id, asset_id, date, side, quantity, price, fees, import_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (account_id, assets[symbol], trade_date, side, quantity, price, fees, digest, store.now()),
            )
            if cursor.rowcount:
                imported += 1
                touched.add(assets[symbol])
                conn.execute(
                    "INSERT OR IGNORE INTO prices (asset_id, date, price, source) VALUES (?, ?, ?, 'trade')",
                    (assets[symbol], trade_date, price),
                )
            else:
                duplicates += 1
        for asset_id in touched:
            store.check_holdings_never_negative(conn, asset_id)
    return {"imported": imported, "duplicates": duplicates, "created_assets": created, "problems": problems[:20]}


# Export


def _money(cents: int) -> str:
    return f"{cents / 100:.2f}"


def export_csv(conn: sqlite3.Connection, kind: str) -> str:
    kind = v.choice(kind, "kind", ("transactions", "trades", "dividends"))
    out = io.StringIO()
    writer = csv.writer(out)
    if kind == "transactions":
        writer.writerow(["date", "account", "payee", "category", "amount", "note", "transfer"])
        for row in conn.execute(
            """SELECT t.date, a.name, t.payee, c.name, t.amount, t.note, t.transfer_group IS NOT NULL
               FROM transactions t JOIN accounts a ON a.id = t.account_id LEFT JOIN categories c ON c.id = t.category_id
               ORDER BY t.date, t.id"""
        ):
            writer.writerow([row[0], row[1], row[2], row[3] or "", _money(row[4]), row[5], "yes" if row[6] else ""])
    elif kind == "trades":
        writer.writerow(TRADE_COLUMNS + ["account", "note"])
        for row in conn.execute(
            """SELECT t.date, a.symbol, t.side, t.quantity, t.price, t.fees, ac.name, t.note
               FROM trades t JOIN assets a ON a.id = t.asset_id JOIN accounts ac ON ac.id = t.account_id
               ORDER BY t.date, t.id"""
        ):
            writer.writerow([row[0], row[1], row[2], f"{row[3]:g}", f"{row[4]:g}", _money(row[5]), row[6], row[7]])
    else:
        writer.writerow(["date", "symbol", "account", "gross", "tax", "net", "note"])
        for row in conn.execute(
            """SELECT d.date, a.symbol, ac.name, d.amount, d.tax, d.note
               FROM dividends d JOIN assets a ON a.id = d.asset_id JOIN accounts ac ON ac.id = d.account_id
               ORDER BY d.date, d.id"""
        ):
            writer.writerow([row[0], row[1], row[2], _money(row[3]), _money(row[4]), _money(row[3] - row[4]), row[5]])
    return out.getvalue()
