import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from coffer.api import Coffer
from coffer.crypto import TEST_KDF
from coffer.devserver import make_handler


@pytest.fixture
def server(tmp_path):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Coffer(tmp_path, kdf=TEST_KDF)))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def post(url, body, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    request = urllib.request.Request(url + "/rpc", data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.headers, json.loads(response.read())


def test_rpc_round_trip_from_the_ui_origin(server):
    headers, body = post(server, {"command": "status"}, origin="http://localhost:1420")
    assert body["ok"]["vault_exists"] is False
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:1420"


def test_other_origins_are_refused(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(server, {"command": "status"}, origin="http://evil.example.com")
    assert exc.value.code == 403


def test_malformed_requests_get_an_error_not_a_crash(server):
    request = urllib.request.Request(server + "/rpc", data=b"not json", method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        assert json.loads(response.read())["error"]["code"] == "invalid"
