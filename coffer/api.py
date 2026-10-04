"""The single entry point the interface talks to.

``Coffer.call(command, args)`` returns ``{"ok": result}`` or
``{"error": {"code", "message"}}``. The desktop window and the development
server both go through it, so they behave the same.

Every command that changes data re-encrypts and saves the vault before it
returns: there is no "unsaved changes" state to lose.
"""

from __future__ import annotations

import base64
import inspect
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import analytics, db, demo, importer, prices, store
from .crypto import KdfParams, wipe
from .errors import CofferError, Invalid, Locked, NoVault, UnknownCommand, VaultExists
from .vault import Envelope, write_atomic

log = logging.getLogger("coffer")

VAULT_NAME = "vault.coffer"


@dataclass
class Session:
    conn: sqlite3.Connection
    data_key: bytearray | None
    envelope: Envelope | None
    path: Path | None
    demo: bool = False
    last_activity: float = field(default_factory=time.monotonic)

    def save(self) -> None:
        if self.demo or self.envelope is None or self.data_key is None or self.path is None:
            return
        self.envelope.reseal(self.data_key, db.dump_database(self.conn))
        self.envelope.write(self.path)

    def close(self) -> None:
        self.conn.close()
        wipe(self.data_key)
        self.data_key = None


@dataclass
class Command:
    handler: Callable[..., Any]
    needs_session: bool
    mutates: bool


COMMANDS: dict[str, Command] = {}


def command(name: str, *, session: bool = True, mutates: bool = False):
    def register(fn):
        COMMANDS[name] = Command(fn, session, mutates)
        return fn

    return register


class Coffer:
    def __init__(self, data_dir: Path, kdf: KdfParams | None = None, clock: Callable[[], float] = time.monotonic):
        self.data_dir = Path(data_dir)
        self.vault_path = self.data_dir / VAULT_NAME
        self.kdf = kdf or KdfParams()
        self.clock = clock
        self.session: Session | None = None
        # pywebview and the dev server call from several threads; one command
        # at a time keeps the in-memory database and the file in step.
        self._lock = threading.RLock()

    # Dispatch

    def call(self, name: str, args: dict | None = None) -> dict:
        with self._lock:
            try:
                return {"ok": self._run(name, args or {})}
            except CofferError as exc:
                return {"error": exc.to_dict()}
            except sqlite3.IntegrityError as exc:
                log.warning("integrity error in %s: %s", name, exc)
                return {"error": {"code": "invalid", "message": "That change conflicts with existing data"}}
            except Exception:
                log.exception("unexpected error in %s", name)
                return {"error": {"code": "internal", "message": "Unexpected error, nothing was changed"}}

    def _run(self, name: str, args: dict) -> Any:
        spec = COMMANDS.get(name)
        if spec is None:
            raise UnknownCommand(f"Unknown command: {name}")
        if not isinstance(args, dict):
            raise Invalid("Arguments must be an object")
        leading = (self, None) if spec.needs_session else (self,)
        try:
            inspect.signature(spec.handler).bind(*leading, **args)
        except TypeError as exc:
            raise Invalid(f"Bad arguments for {name}") from exc
        if spec.needs_session:
            session = self._active_session()
            result = spec.handler(self, session, **args)
            if spec.mutates:
                session.save()
            return result
        return spec.handler(self, **args)

    def _active_session(self) -> Session:
        session = self.session
        if session is None:
            raise Locked()
        if self.clock() - session.last_activity > self._auto_lock_seconds(session):
            self._close_session()
            raise Locked("Locked after a period of inactivity")
        session.last_activity = self.clock()
        return session

    def _auto_lock_seconds(self, session: Session) -> float:
        return store.get_settings(session.conn)["auto_lock_minutes"] * 60

    def _open_session(self, session: Session) -> None:
        self._close_session()
        self.session = session

    def _close_session(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None

    def vault_exists(self) -> bool:
        return self.vault_path.exists()


# Session and vault


@command("status", session=False)
def _status(app: Coffer) -> dict:
    session = app.session
    state = {"vault_exists": app.vault_exists(), "unlocked": False, "demo": False}
    if session is None:
        return state
    remaining = app._auto_lock_seconds(session) - (app.clock() - session.last_activity)
    if remaining <= 0:
        app._close_session()
        return state
    settings = store.get_settings(session.conn)
    return {
        **state,
        "unlocked": True,
        "demo": session.demo,
        "seconds_left": int(remaining),
        "auto_lock_minutes": settings["auto_lock_minutes"],
        "currency": settings["currency"],
        "saved_at": session.envelope.saved_at if session.envelope else None,
    }


@command("create_vault", session=False)
def _create_vault(app: Coffer, password: str) -> dict:
    if app.vault_exists():
        raise VaultExists()
    conn = db.create_database(store.now())
    envelope, data_key, recovery_key = Envelope.create(password, db.dump_database(conn), app.kdf)
    envelope.write(app.vault_path)
    app._open_session(Session(conn, data_key, envelope, app.vault_path, last_activity=app.clock()))
    return {"recovery_key": recovery_key}


def _load(app: Coffer, envelope: Envelope, data_key: bytearray, path: Path) -> Session:
    conn = db.load_database(envelope.decrypt(data_key))
    return Session(conn, data_key, envelope, path, last_activity=app.clock())


@command("unlock", session=False)
def _unlock(app: Coffer, password: str) -> dict:
    if not app.vault_exists():
        raise NoVault()
    envelope = Envelope.read(app.vault_path)
    data_key = envelope.unlock_with_password(password)
    app._open_session(_load(app, envelope, data_key, app.vault_path))
    return _status(app)


@command("recover", session=False)
def _recover(app: Coffer, recovery_key: str, new_password: str) -> dict:
    if not app.vault_exists():
        raise NoVault()
    envelope = Envelope.read(app.vault_path)
    data_key = envelope.unlock_with_recovery_key(recovery_key)
    session = _load(app, envelope, data_key, app.vault_path)
    envelope.set_password(data_key, new_password)
    session.save()
    app._open_session(session)
    return _status(app)


@command("open_demo", session=False)
def _open_demo(app: Coffer) -> dict:
    conn = db.create_database(store.now())
    demo.populate(conn)
    app._open_session(Session(conn, None, None, None, demo=True, last_activity=app.clock()))
    return _status(app)


@command("lock", session=False)
def _lock(app: Coffer) -> dict:
    app._close_session()
    return _status(app)


@command("ping")
def _ping(app: Coffer, session: Session) -> dict:
    return _status(app)


def _require_real_vault(session: Session) -> None:
    if session.demo:
        raise Invalid("Not available in the demo: create your own vault first")


@command("change_password", mutates=True)
def _change_password(app: Coffer, session: Session, current: str, new: str) -> dict:
    _require_real_vault(session)
    session.envelope.unlock_with_password(current)
    if current == new:
        raise Invalid("The new password is the same as the current one")
    session.envelope.set_password(session.data_key, new)
    return {"changed": True}


@command("rotate_recovery_key", mutates=True)
def _rotate_recovery_key(app: Coffer, session: Session, password: str) -> dict:
    _require_real_vault(session)
    session.envelope.unlock_with_password(password)
    return {"recovery_key": session.envelope.rotate_recovery_key(session.data_key)}


def _backup_name() -> str:
    return f"coffer-backup-{datetime.now().strftime('%Y-%m-%d-%H%M')}.coffer"


@command("backup_bytes")
def _backup_bytes(app: Coffer, session: Session) -> dict:
    """The backup is the vault file itself: already encrypted, safe to keep on
    a USB stick or in cloud storage."""
    _require_real_vault(session)
    session.save()
    return {"filename": _backup_name(), "data": base64.b64encode(session.envelope.to_bytes()).decode()}


@command("backup_to_file")
def _backup_to_file(app: Coffer, session: Session, path: str) -> dict:
    _require_real_vault(session)
    session.save()
    target = _writable_path(path)
    write_atomic(target, session.envelope.to_bytes())
    return {"path": str(target)}


@command("restore_backup", session=False)
def _restore_backup(app: Coffer, data: str, password: str) -> dict:
    """Checks that the backup opens with ``password`` before touching the
    current vault, and keeps the current vault next to it rather than
    deleting it."""
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, TypeError) as exc:
        raise Invalid("Could not read the backup file") from exc
    envelope = Envelope.from_bytes(raw)
    data_key = envelope.unlock_with_password(password)
    session = _load(app, envelope, data_key, app.vault_path)
    app._close_session()
    if app.vault_exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        app.vault_path.rename(app.vault_path.with_name(f"vault-replaced-{stamp}.coffer"))
    envelope.write(app.vault_path)
    app._open_session(session)
    return _status(app)


def _writable_path(path: str) -> Path:
    if not isinstance(path, str) or not path.strip():
        raise Invalid("Choose where to save the file")
    target = Path(path).expanduser()
    if not target.is_absolute() or not target.parent.is_dir():
        raise Invalid("That folder does not exist")
    return target


# Settings and records


@command("get_settings")
def _get_settings(app: Coffer, session: Session) -> dict:
    return store.get_settings(session.conn)


@command("update_settings", mutates=True)
def _update_settings(app: Coffer, session: Session, patch: dict) -> dict:
    return store.update_settings(session.conn, patch)


def _simple(name: str, fn: Callable, *, mutates: bool = False, arg: str | None = None) -> None:
    """Registers a command that only forwards one argument to ``store``."""
    if arg is None:
        command(name, mutates=mutates)(lambda app, session: fn(session.conn))
    else:
        def handler(app, session, **kw):
            if set(kw) != {arg}:
                raise Invalid(f"{name} expects '{arg}'")
            return fn(session.conn, kw[arg])

        command(name, mutates=mutates)(handler)


_simple("list_accounts", store.list_accounts)
_simple("save_account", store.save_account, mutates=True, arg="account")
_simple("delete_account", store.delete_account, mutates=True, arg="id")
_simple("list_categories", store.list_categories)
_simple("save_category", store.save_category, mutates=True, arg="category")
_simple("delete_category", store.delete_category, mutates=True, arg="id")
_simple("list_rules", store.list_rules)
_simple("save_rule", store.save_rule, mutates=True, arg="rule")
_simple("delete_rule", store.delete_rule, mutates=True, arg="id")
_simple("apply_rules", store.apply_rules, mutates=True)
_simple("list_transactions", store.list_transactions, arg="query")
_simple("save_transaction", store.save_transaction, mutates=True, arg="transaction")
_simple("save_transfer", store.save_transfer, mutates=True, arg="transfer")
_simple("delete_transaction", store.delete_transaction, mutates=True, arg="id")
_simple("list_assets", store.list_assets)
_simple("save_asset", store.save_asset, mutates=True, arg="asset")
_simple("delete_asset", store.delete_asset, mutates=True, arg="id")
_simple("set_price", store.set_price, mutates=True, arg="price")
_simple("list_prices", store.list_prices, arg="asset_id")
_simple("save_trade", store.save_trade, mutates=True, arg="trade")
_simple("delete_trade", store.delete_trade, mutates=True, arg="id")
_simple("list_dividends", store.list_dividends)
_simple("save_dividend", store.save_dividend, mutates=True, arg="dividend")
_simple("delete_dividend", store.delete_dividend, mutates=True, arg="id")
_simple("refresh_prices", prices.refresh, mutates=True)
_simple("overview", analytics.overview)
_simple("portfolio", analytics.portfolio)
_simple("dividends_summary", analytics.dividends_summary)
_simple("budget_report", analytics.budget_report, arg="month")


@command("list_trades")
def _list_trades(app: Coffer, session: Session, asset_id: int | None = None) -> list:
    return store.list_trades(session.conn, asset_id)


@command("net_worth_series")
def _net_worth_series(app: Coffer, session: Session, months: int | None = None) -> list:
    return analytics.net_worth_series(session.conn, months)


@command("cash_flow")
def _cash_flow(app: Coffer, session: Session, months: int = 12) -> list:
    if not isinstance(months, int) or not 1 <= months <= 60:
        raise Invalid("Months must be between 1 and 60")
    return analytics.cash_flow(session.conn, months)


# Import and export


@command("import_inspect")
def _import_inspect(app: Coffer, session: Session, content: str) -> dict:
    return importer.inspect(content)


@command("import_preview")
def _import_preview(app: Coffer, session: Session, account_id: int, content: str, mapping: dict) -> dict:
    return importer.preview(session.conn, account_id, content, mapping)


@command("import_commit", mutates=True)
def _import_commit(app: Coffer, session: Session, account_id: int, content: str, mapping: dict) -> dict:
    return importer.commit(session.conn, account_id, content, mapping)


@command("import_trades", mutates=True)
def _import_trades(app: Coffer, session: Session, account_id: int, content: str) -> dict:
    return importer.import_trades(session.conn, account_id, content)


@command("export_csv")
def _export_csv(app: Coffer, session: Session, kind: str) -> dict:
    return {"filename": f"coffer-{kind}-{datetime.now():%Y-%m-%d}.csv", "content": importer.export_csv(session.conn, kind)}


@command("export_to_file")
def _export_to_file(app: Coffer, session: Session, kind: str, path: str) -> dict:
    target = _writable_path(path)
    target.write_text(importer.export_csv(session.conn, kind), encoding="utf-8")
    return {"path": str(target)}

