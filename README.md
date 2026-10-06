# Coffer desktop

A private personal finance and investment tracker that runs entirely on your computer. No server, no account, no bank connection: data lives in one encrypted file on the device.

- **Accounts and transactions**: current accounts, savings, cash, credit cards and brokerage accounts; transfers between them; categories with automatic rules.
- **Budget**: monthly limits per category, spending pace against the share of the month gone, twelve months of money in and out.
- **Net worth over time**: cash plus investments valued at the price of each date.
- **Investments**: ETFs, stocks, bonds, funds and crypto; average cost, unrealized and realized gains, dividends with withheld tax, allocation by type and region.
- **CSV import** of bank statements (any delimiter, date format and decimal separator, single or split amount columns) and broker trades, safe to repeat: rows already imported are skipped.
- **Encrypted backups** and CSV export.
- **Demo data**: two years of a fictional person's finances, held in memory and never saved.

Coffer records and analyses. It does not give investment advice.

## Stack

| Part | Technology |
| --- | --- |
| Core | Python 3.11+, SQLite (in memory), `cryptography` (AES-256-GCM), `argon2-cffi` (Argon2id) |
| Window | `pywebview`, using the system web view (WebKit on macOS, WebView2 on Windows, GTK/Qt on Linux) |
| Interface | SvelteKit (static, hash router), Svelte 5, TypeScript, ECharts |

The interface talks to the core through a single function, `rpc(command, args)`, implemented by `coffer/api.py`. In the desktop window it goes through pywebview's JavaScript bridge; during development it goes through a local HTTP server, so the interface can be worked on in a browser with hot reload.

## Getting started

Requirements: Python 3.11 or newer and Node.js 22 or newer. Developed and tested on macOS; pywebview also supports Windows and Linux.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
(cd ui && npm install && npm run build)
.venv/bin/python -m coffer
```

The vault is stored in the user data folder (`~/Library/Application Support/Coffer` on macOS, `%APPDATA%\Coffer` on Windows, `~/.local/share/coffer` on Linux). Set `COFFER_DATA_DIR` to use another folder.

### Working on the interface

Run the core and the interface in two terminals, then open http://localhost:1420:

```bash
.venv/bin/python -m coffer.devserver
```

```bash
cd ui && npm run dev
```

The development server listens on `127.0.0.1:1430` only, accepts requests only from the interface's origin, and keeps its vault in `.dev-data/`. To see the interface inside the real window with hot reload, run `COFFER_UI_URL=http://localhost:1420 .venv/bin/python -m coffer`. `COFFER_DEBUG=1` enables the web inspector and logs command names (never their arguments).

### Tests

```bash
.venv/bin/python -m pytest
(cd ui && npm run check)
```

## Security model

| What | How |
| --- | --- |
| Storage | One file, `vault.coffer`. The SQLite database is serialized in memory and encrypted with AES-256-GCM before it touches the disk; a clear copy is never written. |
| Keys | A random 256-bit data key encrypts the database. It is stored twice: wrapped by a key derived from the master password with Argon2id (64 MiB, 3 passes), and wrapped by a key derived from the recovery key. Changing the password rewraps the data key without re-encrypting the data. |
| Integrity | Every ciphertext carries associated data naming its role, so slots and payload cannot be swapped, and any change to the file is detected. |
| Writes | Every change is saved before the command returns, through a temporary file that is flushed and renamed over the vault: a crash leaves the old vault or the new one, never half of one. On macOS and Linux the file is created with owner-only permissions. |
| Recovery | A 160-bit recovery key (Crockford base32, 8 groups of 4) is shown once when the vault is created. Without the password or the recovery key the data cannot be opened by anyone. |
| Auto-lock | After a configurable period without activity (5 minutes by default) the core drops the database and the key from memory. The window reports activity; the core decides. |
| Network | Only when updating prices, and only for assets set to an online source: the ticker symbols are sent to Yahoo Finance's chart endpoint or CoinGecko's simple price API. No amounts, accounts or identifiers. Offline mode turns this off entirely. |
| Exports | CSV exports are not encrypted, and the interface says so before writing one. Backups are copies of the encrypted vault. |
| Web view | Runs in private mode, so it keeps no cookies or storage between launches. |

Python cannot guarantee that secrets are wiped from memory: keys are overwritten on lock as a best effort, and the operating system's protections (disk encryption, screen lock) remain the first line of defence.

## Money and investments

- Amounts are stored as integer cents. Unit prices and quantities are floating point; trade values are rounded to cents the same way in Python and SQL.
- Account balances and the net worth history are both computed from one SQL view, `cash_flows` (transactions, trade settlements, net dividends), so they always agree.
- A buy takes its value plus fees from the brokerage account's cash; a sale adds its value minus fees; dividends add the net amount. Fund a brokerage account with a transfer.
- Holdings use the average cost method. A sale that would take a position below zero at any date is refused.
- Spending excludes transfers. A positive amount in a spending category is a refund and reduces that category.
- One currency per vault, chosen in Settings. Nothing is converted, so online prices must be quoted in the same currency.

## Importing CSV files

**Bank statements**: Coffer detects the delimiter, the header, the date format and the likely columns, then shows a preview with duplicates and unreadable rows before anything is saved. Each row is identified by its date, amount, description and position among identical rows, so importing the same file twice adds nothing, while two identical purchases on the same day are both kept. Category rules are applied on import.

**Broker trades** use a fixed layout:

```
date,symbol,side,quantity,price,fees
2026-03-02,GEQ,buy,4.25,97.40,1.00
```

Unknown symbols become new assets with manual prices. Examples of both are in [`samples`](samples).

## Project layout

```
coffer/
  api.py         command registry, sessions, auto-lock, save after every change
  crypto.py      Argon2id, AES-256-GCM, recovery keys
  vault.py       the encrypted file format and atomic writes
  db.py          schema and the cash_flows view
  store.py       records and their checks
  analytics.py   net worth, budgets, cash flow, holdings, dividends
  importer.py    CSV import and export
  prices.py      online prices
  demo.py        demo data
  desktop.py     the pywebview window
  devserver.py   local HTTP bridge for development
ui/              SvelteKit interface
samples/         example CSV files
tests/
```

## Data and assets

All names in the demo data and samples (people, employers, shops, banks, brokers and instruments) are fictional, and demo prices are simulated. The interface uses system fonts and icons drawn for this project; there are no third-party images.

## License

The code is released under the [MIT License](LICENSE).

Part of the [`templates`](https://github.com/mattoznav/templates) collection.
