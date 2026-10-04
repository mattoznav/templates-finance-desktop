import pytest

from coffer import db, store
from coffer.api import Coffer
from coffer.crypto import TEST_KDF

PASSWORD = "correct horse battery"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def app(tmp_path, clock):
    return Coffer(tmp_path, kdf=TEST_KDF, clock=clock)


@pytest.fixture
def unlocked(app):
    result = app.call("create_vault", {"password": PASSWORD})
    assert "ok" in result
    return app


@pytest.fixture
def conn():
    connection = db.create_database(store.now())
    yield connection
    connection.close()


def ok(result):
    assert "ok" in result, result
    return result["ok"]


def err(result):
    assert "error" in result, result
    return result["error"]["code"]
