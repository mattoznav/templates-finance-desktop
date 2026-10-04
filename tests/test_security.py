import base64
import json

import pytest

from coffer import crypto
from coffer.api import Coffer
from coffer.crypto import TEST_KDF
from coffer.errors import Corrupt, WrongPassword, WrongRecoveryKey
from coffer.vault import Envelope

from .conftest import PASSWORD, err, ok


def test_seal_round_trip_and_tamper_detection():
    key = crypto.random_key()
    nonce, ct = crypto.seal(key, b"hello", b"aad")
    assert crypto.open_sealed(key, nonce, ct, b"aad") == b"hello"
    assert crypto.open_sealed(crypto.random_key(), nonce, ct, b"aad") is None
    assert crypto.open_sealed(key, nonce, ct, b"other") is None
    tampered = bytes([ct[0] ^ 1]) + ct[1:]
    assert crypto.open_sealed(key, nonce, tampered, b"aad") is None


def test_recovery_key_format_and_normalization():
    key = crypto.new_recovery_key()
    assert len(key) == 39 and key.count("-") == 7
    assert crypto.normalize_recovery_key(key.lower().replace("-", " ")) == key.replace("-", "")
    with pytest.raises(WrongRecoveryKey):
        crypto.normalize_recovery_key("ABCD")
    with pytest.raises(WrongRecoveryKey):
        crypto.normalize_recovery_key("U" * 32)


def test_envelope_unlocks_with_password_or_recovery_key_only():
    envelope, key, recovery = Envelope.create(PASSWORD, b"database", TEST_KDF)
    restored = Envelope.from_bytes(envelope.to_bytes())
    assert restored.decrypt(restored.unlock_with_password(PASSWORD)) == b"database"
    assert restored.decrypt(restored.unlock_with_recovery_key(recovery)) == b"database"
    with pytest.raises(WrongPassword):
        restored.unlock_with_password("wrong password!")
    with pytest.raises(WrongRecoveryKey):
        restored.unlock_with_recovery_key(crypto.new_recovery_key())


def test_slots_cannot_be_swapped():
    envelope, _, _ = Envelope.create(PASSWORD, b"database", TEST_KDF)
    envelope.recovery_slot = envelope.password_slot
    with pytest.raises(WrongRecoveryKey):
        envelope.unlock_with_recovery_key(crypto.new_recovery_key())


def test_corrupt_files_are_rejected():
    with pytest.raises(Corrupt):
        Envelope.from_bytes(b"not json")
    with pytest.raises(Corrupt):
        Envelope.from_bytes(json.dumps({"format": "something-else", "version": 1}).encode())
    envelope, key, _ = Envelope.create(PASSWORD, b"database", TEST_KDF)
    document = json.loads(envelope.to_bytes())
    ct = base64.b64decode(document["payload"]["ciphertext"])
    document["payload"]["ciphertext"] = base64.b64encode(bytes([ct[0] ^ 1]) + ct[1:]).decode()
    tampered = Envelope.from_bytes(json.dumps(document).encode())
    with pytest.raises(Corrupt):
        tampered.decrypt(tampered.unlock_with_password(PASSWORD))


def test_short_passwords_are_refused(app):
    assert err(app.call("create_vault", {"password": "short"})) == "invalid"
    assert not app.vault_exists()


def test_vault_file_never_contains_clear_data(unlocked):
    ok(unlocked.call("save_account", {"account": {"name": "Secret Savings Account", "kind": "savings"}}))
    raw = unlocked.vault_path.read_bytes()
    assert b"Secret Savings" not in raw
    assert b"SQLite format" not in raw
    assert oct(unlocked.vault_path.stat().st_mode & 0o777) == "0o600"
    assert [p.name for p in unlocked.data_dir.iterdir()] == ["vault.coffer"]


def test_changes_survive_lock_and_unlock(unlocked):
    ok(unlocked.call("save_account", {"account": {"name": "Everyday", "kind": "checking", "opening_balance": 12345}}))
    ok(unlocked.call("lock"))
    assert err(unlocked.call("list_accounts")) == "locked"
    assert err(unlocked.call("unlock", {"password": "wrong password"})) == "wrong_password"
    ok(unlocked.call("unlock", {"password": PASSWORD}))
    accounts = ok(unlocked.call("list_accounts"))
    assert [(a["name"], a["balance"]) for a in accounts] == [("Everyday", 12345)]


def test_a_new_process_reads_the_same_vault(unlocked, tmp_path):
    ok(unlocked.call("save_account", {"account": {"name": "Everyday", "kind": "checking"}}))
    fresh = Coffer(tmp_path, kdf=TEST_KDF)
    assert ok(fresh.call("status"))["vault_exists"] is True
    ok(fresh.call("unlock", {"password": PASSWORD}))
    assert len(ok(fresh.call("list_accounts"))) == 1


def test_auto_lock_after_inactivity(unlocked, clock):
    ok(unlocked.call("update_settings", {"patch": {"auto_lock_minutes": 2}}))
    clock.now += 119
    ok(unlocked.call("ping"))
    clock.now += 119
    ok(unlocked.call("list_accounts"))
    clock.now += 121
    assert err(unlocked.call("list_accounts")) == "locked"
    assert ok(unlocked.call("status"))["unlocked"] is False


def test_status_does_not_count_as_activity(unlocked, clock):
    clock.now += 200
    ok(unlocked.call("status"))
    clock.now += 101
    assert ok(unlocked.call("status"))["unlocked"] is False


def test_recovery_key_resets_the_password(app):
    recovery = ok(app.call("create_vault", {"password": PASSWORD}))["recovery_key"]
    ok(app.call("save_account", {"account": {"name": "Everyday", "kind": "checking"}}))
    ok(app.call("lock"))
    assert err(app.call("recover", {"recovery_key": "0000-0000-0000-0000-0000-0000-0000-0000", "new_password": "a brand new one"})) == "wrong_recovery_key"
    ok(app.call("recover", {"recovery_key": recovery.lower(), "new_password": "a brand new one"}))
    ok(app.call("lock"))
    assert err(app.call("unlock", {"password": PASSWORD})) == "wrong_password"
    ok(app.call("unlock", {"password": "a brand new one"}))
    assert len(ok(app.call("list_accounts"))) == 1


def test_change_password_and_rotate_recovery_key(app):
    old_recovery = ok(app.call("create_vault", {"password": PASSWORD}))["recovery_key"]
    assert err(app.call("change_password", {"current": "nope nope nope", "new": "another password"})) == "wrong_password"
    ok(app.call("change_password", {"current": PASSWORD, "new": "another password"}))
    new_recovery = ok(app.call("rotate_recovery_key", {"password": "another password"}))["recovery_key"]
    ok(app.call("lock"))
    ok(app.call("unlock", {"password": "another password"}))
    ok(app.call("lock"))
    assert err(app.call("recover", {"recovery_key": old_recovery, "new_password": "whatever it is"})) == "wrong_recovery_key"
    ok(app.call("recover", {"recovery_key": new_recovery, "new_password": "whatever it is"}))


def test_backup_and_restore(unlocked, tmp_path):
    ok(unlocked.call("save_account", {"account": {"name": "Before backup", "kind": "checking"}}))
    backup = ok(unlocked.call("backup_bytes"))
    assert backup["filename"].endswith(".coffer")
    ok(unlocked.call("save_account", {"account": {"name": "After backup", "kind": "checking"}}))

    assert err(unlocked.call("restore_backup", {"data": backup["data"], "password": "wrong password"})) == "wrong_password"
    # A failed restore leaves the session and the vault alone.
    assert len(ok(unlocked.call("list_accounts"))) == 2

    ok(unlocked.call("restore_backup", {"data": backup["data"], "password": PASSWORD}))
    assert [a["name"] for a in ok(unlocked.call("list_accounts"))] == ["Before backup"]
    replaced = [p.name for p in tmp_path.iterdir() if p.name.startswith("vault-replaced-")]
    assert len(replaced) == 1


def test_backup_to_file_is_the_encrypted_vault(unlocked, tmp_path):
    target = tmp_path / "out" / "backup.coffer"
    target.parent.mkdir()
    ok(unlocked.call("backup_to_file", {"path": str(target)}))
    envelope = Envelope.read(target)
    envelope.unlock_with_password(PASSWORD)
    assert err(unlocked.call("backup_to_file", {"path": "relative/path.coffer"})) == "invalid"


def test_demo_never_writes_to_disk(app):
    ok(app.call("open_demo"))
    ok(app.call("save_account", {"account": {"name": "Demo change", "kind": "cash"}}))
    assert list(app.data_dir.iterdir()) == []
    assert err(app.call("backup_bytes")) == "invalid"


def test_creating_a_second_vault_is_refused(unlocked):
    assert err(unlocked.call("create_vault", {"password": "another password"})) == "vault_exists"


def test_bad_arguments_are_reported_not_crashed(unlocked):
    assert err(unlocked.call("save_account", {"wrong": 1})) == "invalid"
    assert err(unlocked.call("cash_flow", {"months": "twelve"})) == "invalid"
    assert err(unlocked.call("does_not_exist")) == "unknown_command"
