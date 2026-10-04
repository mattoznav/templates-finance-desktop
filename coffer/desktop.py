"""Desktop window: the built interface rendered by the system web view, with
the Python core exposed to it as ``window.pywebview.api``."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import webview

from .api import Coffer

log = logging.getLogger("coffer.desktop")

UI_INDEX = Path(__file__).resolve().parent.parent / "ui" / "build" / "index.html"


def data_dir() -> Path:
    """Where the vault lives. ``COFFER_DATA_DIR`` overrides it."""
    override = os.environ.get("COFFER_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Coffer"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "Coffer"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "coffer"


class Bridge:
    """Public methods become JavaScript functions. Attributes starting with an
    underscore are not exposed."""

    def __init__(self, app: Coffer):
        self._app = app
        self._window: webview.Window | None = None

    def rpc(self, command: str, args: dict | None = None) -> dict:
        # Only the command name is logged: arguments can hold passwords.
        log.debug("rpc %s", command)
        return self._app.call(command, args or {})

    def choose_save_path(self, filename: str) -> str | None:
        if self._window is None:
            return None
        result = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=filename)
        if not result:
            return None
        return result if isinstance(result, str) else result[0]


def main() -> None:
    debug = bool(os.environ.get("COFFER_DEBUG"))
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # During development the window can load the Vite dev server instead.
    url = os.environ.get("COFFER_UI_URL")
    if not url:
        if not UI_INDEX.exists():
            sys.exit("The interface is not built yet: run `npm run build` in the ui folder.")
        url = str(UI_INDEX)
    bridge = Bridge(Coffer(data_dir()))
    window = webview.create_window(
        "Coffer",
        url,
        js_api=bridge,
        width=1320,
        height=860,
        min_size=(1040, 700),
        background_color="#101214",
        text_select=True,
    )
    bridge._window = window
    # private_mode keeps the web view from persisting cookies or storage.
    webview.start(http_server=not url.startswith("http"), private_mode=True, debug=debug)


if __name__ == "__main__":
    main()
