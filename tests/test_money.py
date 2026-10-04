from datetime import date, timedelta

import pytest

from coffer import analytics, importer, store
from coffer.errors import Invalid

TODAY = date.today()


def d(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


def account(conn, name="Everyday", kind="checking", opening=0, opening_date=None):
    return store.save_account(conn, {"name": name, "kind": kind, "opening_balance": opening, "opening_date": opening_date or d(400)})["id"]


def category(conn, name):
    return next(c["id"] for c in store.list_categories(conn) if c["name"] == name)


def asset(conn, symbol="GEQ"):
    return store.save_asset(conn, {"symbol": symbol, "name": symbol, "kind": "etf", "region": "global"})["id"]


# Accounts and transactions


def test_balance_includes_opening_transactions_trades_and_dividends(conn):
    broker = account(conn, "Broker", "brokerage", opening=100_000)
    a = asset(conn)
    store.save_transaction(conn, {"account_id": broker, "date": d(30), "amount": -1_000, "payee": "Fee"})
    store.save_trade(conn, {"account_id": broker, "asset_id": a, "date": d(20), "side": "buy", "quantity": 3, "price": 100.005, "fees": 150})
    store.save_dividend(conn, {"account_id": broker, "asset_id": a, "date": d(10), "amount": 500, "tax": 130})
    # 1000.00 - 10.00 - (300.02 + 1.50) + (5.00 - 1.30); 300.015 rounds half up to 300.02
    assert store.list_accounts(conn)[0]["balance"] == 100_000 - 1_000 - 30_002 - 150 + 370


def test_transfers_create_two_linked_rows_and_delete_together(conn):
    a, b = account(conn, "A"), account(conn, "B", "savings")
    store.save_transfer(conn, {"from_account_id": a, "to_account_id": b, "amount": 5_000, "date": d(1)})
    balances = {x["name"]: x["balance"] for x in store.list_accounts(conn)}
    assert balances == {"A": -5_000, "B": 5_000}
    listed = store.list_transactions(conn, {"account_id": a})["items"][0]
    assert listed["counter_account_name"] == "B"
    with pytest.raises(Invalid):
        store.save_transaction(conn, {**listed, "amount": -1})
    store.delete_transaction(conn, listed["id"])
    assert store.list_transactions(conn, {})["total"] == 0


def test_transfer_to_same_account_is_refused(conn):
    a = account(conn)
    with pytest.raises(Invalid):
        store.save_transfer(conn, {"from_account_id": a, "to_account_id": a, "amount": 1, "date": d(1)})


def test_deleting_an_account_removes_the_other_side_of_its_transfers(conn):
    a, b = account(conn, "A"), account(conn, "B")
    store.save_transfer(conn, {"from_account_id": a, "to_account_id": b, "amount": 5_000, "date": d(1)})
    store.delete_account(conn, a)
    assert store.list_accounts(conn)[0]["balance"] == 0


def test_income_category_cannot_take_money_out(conn):
    a = account(conn)
    with pytest.raises(Invalid):
        store.save_transaction(conn, {"account_id": a, "date": d(1), "amount": -100, "payee": "x", "category_id": category(conn, "Salary")})


def test_transaction_filters(conn):
    a = account(conn)
    groceries = category(conn, "Groceries")
    store.save_transaction(conn, {"account_id": a, "date": d(3), "amount": -2_500, "payee": "Greenmarket", "category_id": groceries})
    store.save_transaction(conn, {"account_id": a, "date": d(2), "amount": -900, "payee": "Cafe"})
    store.save_transaction(conn, {"account_id": a, "date": d(1), "amount": 200_000, "payee": "Payroll"})
    assert store.list_transactions(conn, {"search": "green"})["total"] == 1
    assert store.list_transactions(conn, {"category_id": "none"})["total"] == 2
    page = store.list_transactions(conn, {"category_id": groceries})
    assert page["expenses"] == -2_500 and page["income"] == 0
    assert store.list_transactions(conn, {"from": d(2), "to": d(2)})["items"][0]["payee"] == "Cafe"


def test_rules_categorize_by_payee_and_respect_sign(conn):
    a = account(conn)
    store.save_rule(conn, {"pattern": "greenmarket", "category_id": category(conn, "Groceries")})
    store.save_rule(conn, {"pattern": "payroll", "category_id": category(conn, "Salary")})
    store.save_transaction(conn, {"account_id": a, "date": d(1), "amount": -1_000, "payee": "GREENMARKET 042"})
    store.save_transaction(conn, {"account_id": a, "date": d(1), "amount": 1_000, "payee": "Greenmarket refund"})
    store.save_transaction(conn, {"account_id": a, "date": d(1), "amount": 300_000, "payee": "Payroll October"})
    assert store.apply_rules(conn) == 3
    names = {t["payee"]: t["category_name"] for t in store.list_transactions(conn, {})["items"]}
    assert names == {"GREENMARKET 042": "Groceries", "Greenmarket refund": "Groceries", "Payroll October": "Salary"}


# Investments


def test_average_cost_and_realized_gain(conn):
    broker = account(conn, "Broker", "brokerage")
    a = asset(conn)
    store.save_trade(conn, {"account_id": broker, "asset_id": a, "date": d(30), "side": "buy", "quantity": 10, "price": 100, "fees": 0})
    store.save_trade(conn, {"account_id": broker, "asset_id": a, "date": d(20), "side": "buy", "quantity": 10, "price": 120, "fees": 0})
    store.save_trade(conn, {"account_id": broker, "asset_id": a, "date": d(10), "side": "sell", "quantity": 5, "price": 150, "fees": 500})
    store.set_price(conn, {"asset_id": a, "date": d(0), "price": 130})
    holding = analytics.portfolio(conn)["holdings"][0]
    assert holding["quantity"] == 15
    assert holding["average_cost"] == pytest.approx(110)
    assert holding["cost"] == 165_000
    assert holding["value"] == 195_000
    assert holding["unrealized"] == 30_000
    # 5 x 150 - 5.00 fees - 5 x 110 cost
    assert holding["realized"] == 75_000 - 500 - 55_000


def test_selling_more_than_held_is_refused_at_any_date(conn):
    broker = account(conn, "Broker", "brokerage")
    a = asset(conn)
    store.save_trade(conn, {"account_id": broker, "asset_id": a, "date": d(10), "side": "buy", "quantity": 2, "price": 10})
    with pytest.raises(Invalid):
        store.save_trade(conn, {"account_id": broker, "asset_id": a, "date": d(20), "side": "sell", "quantity": 1, "price": 10})
    sell = store.save_trade(conn, {"account_id": broker, "asset_id": a, "date": d(5), "side": "sell", "quantity": 2, "price": 10})
    buy = store.list_trades(conn)[-1]
    with pytest.raises(Invalid):
        store.delete_trade(conn, buy["id"])
    assert len(store.list_trades(conn)) == 2
    store.delete_trade(conn, sell["id"])


def test_allocation_weights_sum_to_one(conn):
    broker = account(conn, "Broker", "brokerage")
    eq = asset(conn, "EQ")
    bond = store.save_asset(conn, {"symbol": "BD", "name": "Bond", "kind": "bond", "region": "europe"})["id"]
    store.save_trade(conn, {"account_id": broker, "asset_id": eq, "date": d(5), "side": "buy", "quantity": 3, "price": 100})
    store.save_trade(conn, {"account_id": broker, "asset_id": bond, "date": d(5), "side": "buy", "quantity": 1, "price": 100})
    allocation = analytics.portfolio(conn)["allocation"]
    assert {g["key"]: g["weight"] for g in allocation["kind"]} == {"etf": 0.75, "bond": 0.25}
    assert sum(g["weight"] for g in allocation["region"]) == pytest.approx(1)


def test_asset_with_trades_cannot_be_deleted(conn):
    broker = account(conn, "Broker", "brokerage")
    a = asset(conn)
    store.save_trade(conn, {"account_id": broker, "asset_id": a, "date": d(5), "side": "buy", "quantity": 1, "price": 1})
    with pytest.raises(Invalid):
        store.delete_asset(conn, a)


# Analytics


def test_net_worth_series_values_holdings_at_the_price_of_each_date(conn):
    broker = account(conn, "Broker", "brokerage", opening=10_000_00, opening_date=d(100))
    a = asset(conn)
    store.save_trade(conn, {"account_id": broker, "asset_id": a, "date": d(90), "side": "buy", "quantity": 10, "price": 100})
    store.set_price(conn, {"asset_id": a, "date": d(50), "price": 150})
    series = analytics.net_worth_series(conn)
    last = series[-1]
    assert last["date"] == TODAY.isoformat()
    assert last["cash"] == 9_000_00
    assert last["investments"] == 1_500_00
    assert last["net_worth"] == 10_500_00
    assert last["cost_basis"] == 1_000_00
    assert series[0]["net_worth"] in (10_000_00, 9_000_00 + 1_000_00)


def test_budget_report_counts_refunds_and_ignores_transfers(conn):
    a, b = account(conn, "A"), account(conn, "B")
    groceries = category(conn, "Groceries")
    store.save_category(conn, {**next(c for c in store.list_categories(conn) if c["id"] == groceries), "monthly_budget": 30_000})
    month = analytics.current_month()
    first = f"{month}-01"
    store.save_transaction(conn, {"account_id": a, "date": first, "amount": -10_000, "payee": "Shop", "category_id": groceries})
    store.save_transaction(conn, {"account_id": a, "date": first, "amount": 2_000, "payee": "Shop refund", "category_id": groceries})
    store.save_transaction(conn, {"account_id": a, "date": first, "amount": 250_000, "payee": "Payroll", "category_id": category(conn, "Salary")})
    store.save_transfer(conn, {"from_account_id": a, "to_account_id": b, "amount": 50_000, "date": first})
    report = analytics.budget_report(conn, month)
    line = next(line for line in report["lines"] if line["name"] == "Groceries")
    assert line["spent"] == 8_000 and line["remaining"] == 22_000
    assert report["totals"]["income"] == 250_000
    assert report["totals"]["expenses"] == 8_000
    assert report["totals"]["savings_rate"] == pytest.approx(242_000 / 250_000)


def test_month_helpers():
    assert analytics.shift_month("2026-01", -1) == "2025-12"
    assert analytics.shift_month("2025-12", 1) == "2026-01"
    assert analytics.month_bounds("2028-02") == ("2028-02-01", "2028-02-29")


def test_demo_data_is_consistent(conn):
    from coffer import demo

    demo.populate(conn)
    accounts = store.list_accounts(conn)
    assert all(a["balance"] > -50_000 for a in accounts if a["kind"] != "credit_card")
    overview = analytics.overview(conn)
    assert overview["net_worth"] > 0 and overview["series"]
    portfolio = analytics.portfolio(conn)
    assert all(h["quantity"] >= 0 for h in portfolio["holdings"])
    assert portfolio["totals"]["dividends"] > 0


# CSV


@pytest.mark.parametrize(
    "text, expected",
    [
        ("12.30", 1230),
        ("-12.30", -1230),
        ("1.234,56", 123456),
        ("1,234.56", 123456),
        ("-1.234.567,8", -123456780),
        ("€ 7", 700),
        ("(45.00)", -4500),
        ("12,5-", -1250),
        ("0,99", 99),
    ],
)
def test_parse_amount(text, expected):
    assert importer.parse_amount(text) == expected


ITALIAN_BANK = """Data;Descrizione;Uscite;Entrate
03/09/2026;GREENMARKET 042;25,40;
03/09/2026;GREENMARKET 042;25,40;
05/09/2026;Fieldstone Studio payroll;;3.180,00
07/09/2026;broken row;abc;
"""


def test_inspect_guesses_an_italian_bank_layout():
    result = importer.inspect(ITALIAN_BANK)
    mapping = result["mapping"]
    assert mapping["delimiter"] == ";"
    assert mapping["has_header"] is True
    assert mapping["date_column"] == 0 and mapping["date_format"] == "%d/%m/%Y"
    assert mapping["amount_mode"] == "split"
    assert (mapping["debit_column"], mapping["credit_column"], mapping["payee_column"]) == (2, 3, 1)


def test_import_is_idempotent_and_keeps_identical_rows(conn):
    a = account(conn)
    store.save_rule(conn, {"pattern": "greenmarket", "category_id": category(conn, "Groceries")})
    mapping = importer.inspect(ITALIAN_BANK)["mapping"]
    preview = importer.preview(conn, a, ITALIAN_BANK, mapping)
    assert (preview["new"], preview["duplicate"], preview["error"]) == (3, 0, 1)
    assert preview["rows"][0]["category"] == "Groceries"
    assert importer.commit(conn, a, ITALIAN_BANK, mapping) == {"imported": 3, "duplicates": 0, "errors": 1}
    assert importer.commit(conn, a, ITALIAN_BANK, mapping) == {"imported": 0, "duplicates": 3, "errors": 1}
    assert store.list_accounts(conn)[0]["balance"] == 318_000 - 2 * 2_540


def test_import_single_amount_column_with_inverted_sign(conn):
    a = account(conn)
    content = "date,amount,payee\n2026-09-01,25.00,Card purchase\n2026-09-02,-100.00,Card payment\n"
    mapping = importer.inspect(content)["mapping"]
    assert mapping["amount_column"] == 1
    importer.commit(conn, a, content, {**mapping, "invert": True})
    assert store.list_accounts(conn)[0]["balance"] == 7_500


def test_import_trades_creates_assets_and_skips_duplicates(conn):
    broker = account(conn, "Broker", "brokerage")
    content = "date,symbol,side,quantity,price,fees\n2026-01-05,VXX,buy,2,50.5,1.00\n2026-02-05,VXX,sell,1,55,1\nbad,row\n"
    result = importer.import_trades(conn, broker, content)
    assert result["imported"] == 2 and result["created_assets"] == 1 and len(result["problems"]) == 1
    assert importer.import_trades(conn, broker, content)["duplicates"] == 2
    with pytest.raises(Invalid):
        importer.import_trades(conn, broker, "a,b\n1,2\n")


def test_import_trades_rejects_overselling(conn):
    broker = account(conn, "Broker", "brokerage")
    with pytest.raises(Invalid):
        importer.import_trades(conn, broker, "date,symbol,side,quantity,price,fees\n2026-01-05,VXX,sell,2,50,0\n")
    assert store.list_trades(conn) == []


def test_export_round_trips_amounts(conn):
    a = account(conn)
    store.save_transaction(conn, {"account_id": a, "date": "2026-09-01", "amount": -1_234, "payee": 'Quote "and", comma'})
    lines = importer.export_csv(conn, "transactions").splitlines()
    assert lines[0].startswith("date,account,payee")
    assert lines[1] == '2026-09-01,Everyday,"Quote ""and"", comma",,-12.34,,'
