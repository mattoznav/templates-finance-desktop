"""The vault file.

A vault is one JSON document. The database is encrypted with a random data
key; that key is stored twice, wrapped once by a key derived from the master
password and once by a key derived from the recovery key. Changing the
password only rewraps the data key, it never re-encrypts the data.

    {
      "format": "coffer-vault", "version": 1,
      "kdf": {...},
      "password_slot": {"salt", "nonce", "wrapped_key"},
      "recovery_slot": {"salt", "nonce", "wrapped_key"},
      "payload": {"nonce", "ciphertext"},
      "saved_at": "..."
    }

Binary fields are base64. Every ciphertext carries associated data naming its
role, so a slot cannot be swapped with the payload or with another slot.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import crypto
from .crypto import KdfParams
from .errors import Corrupt, Invalid, WrongPassword, WrongRecoveryKey

FORMAT = "coffer-vault"
VERSION = 1
AAD_PASSWORD = b"coffer-vault/v1/password-slot"
AAD_RECOVERY = b"coffer-vault/v1/recovery-slot"
AAD_PAYLOAD = b"coffer-vault/v1/payload"

MIN_PASSWORD_LENGTH = 10


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    try:
        return base64.b64decode(text, validate=True)
    except (ValueError, TypeError) as exc:
        raise Corrupt() from exc


@dataclass
class Slot:
    salt: bytes
    nonce: bytes
    wrapped_key: bytes

    @classmethod
    def wrap(cls, secret: bytes, data_key: bytearray, kdf: KdfParams, aad: bytes) -> "Slot":
        salt = crypto.random_bytes(crypto.SALT_LEN)
        kek = crypto.derive_key(secret, salt, kdf)
        try:
            nonce, wrapped = crypto.seal(kek, bytes(data_key), aad)
        finally:
            crypto.wipe(kek)
        return cls(salt, nonce, wrapped)

    def unwrap(self, secret: bytes, kdf: KdfParams, aad: bytes) -> bytearray | None:
        kek = crypto.derive_key(secret, self.salt, kdf)
        try:
            key = crypto.open_sealed(kek, self.nonce, self.wrapped_key, aad)
        finally:
            crypto.wipe(kek)
        return bytearray(key) if key is not None and len(key) == crypto.KEY_LEN else None

    def to_dict(self) -> dict:
        return {"salt": _b64(self.salt), "nonce": _b64(self.nonce), "wrapped_key": _b64(self.wrapped_key)}

    @classmethod
    def from_dict(cls, data: dict) -> "Slot":
        return cls(_unb64(data["salt"]), _unb64(data["nonce"]), _unb64(data["wrapped_key"]))


@dataclass
class Envelope:
    kdf: KdfParams
    password_slot: Slot
    recovery_slot: Slot
    payload_nonce: bytes
    payload: bytes
    saved_at: str

    # Creation and unlocking

    @classmethod
    def create(cls, password: str, database: bytes, kdf: KdfParams | None = None) -> tuple["Envelope", bytearray, str]:
        """Returns the envelope, the data key and the recovery key. The
        recovery key is shown once and never stored in clear."""
        check_password(password)
        kdf = kdf or KdfParams()
        data_key = crypto.random_key()
        recovery_key = crypto.new_recovery_key()
        envelope = cls(
            kdf=kdf,
            password_slot=Slot.wrap(password.encode(), data_key, kdf, AAD_PASSWORD),
            recovery_slot=Slot.wrap(crypto.normalize_recovery_key(recovery_key).encode(), data_key, kdf, AAD_RECOVERY),
            payload_nonce=b"",
            payload=b"",
            saved_at="",
        )
        envelope.reseal(data_key, database)
        return envelope, data_key, recovery_key

    def unlock_with_password(self, password: str) -> bytearray:
        key = self.password_slot.unwrap(password.encode(), self.kdf, AAD_PASSWORD)
        if key is None:
            raise WrongPassword()
        return key

    def unlock_with_recovery_key(self, recovery_key: str) -> bytearray:
        secret = crypto.normalize_recovery_key(recovery_key).encode()
        key = self.recovery_slot.unwrap(secret, self.kdf, AAD_RECOVERY)
        if key is None:
            raise WrongRecoveryKey()
        return key

    def decrypt(self, data_key: bytearray) -> bytes:
        database = crypto.open_sealed(data_key, self.payload_nonce, self.payload, AAD_PAYLOAD)
        if database is None:
            raise Corrupt()
        return database

    # Changes

    def reseal(self, data_key: bytearray, database: bytes) -> None:
        self.payload_nonce, self.payload = crypto.seal(data_key, database, AAD_PAYLOAD)
        self.saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def set_password(self, data_key: bytearray, password: str) -> None:
        check_password(password)
        self.password_slot = Slot.wrap(password.encode(), data_key, self.kdf, AAD_PASSWORD)

    def rotate_recovery_key(self, data_key: bytearray) -> str:
        recovery_key = crypto.new_recovery_key()
        secret = crypto.normalize_recovery_key(recovery_key).encode()
        self.recovery_slot = Slot.wrap(secret, data_key, self.kdf, AAD_RECOVERY)
        return recovery_key

    # Serialization

    def to_bytes(self) -> bytes:
        document = {
            "format": FORMAT,
            "version": VERSION,
            "kdf": self.kdf.to_dict(),
            "password_slot": self.password_slot.to_dict(),
            "recovery_slot": self.recovery_slot.to_dict(),
            "payload": {"nonce": _b64(self.payload_nonce), "ciphertext": _b64(self.payload)},
            "saved_at": self.saved_at,
        }
        return json.dumps(document, indent=1).encode()

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Envelope":
        try:
            document = json.loads(raw)
            if document.get("format") != FORMAT or document.get("version") != VERSION:
                raise Corrupt()
            return cls(
                kdf=KdfParams.from_dict(document["kdf"]),
                password_slot=Slot.from_dict(document["password_slot"]),
                recovery_slot=Slot.from_dict(document["recovery_slot"]),
                payload_nonce=_unb64(document["payload"]["nonce"]),
                payload=_unb64(document["payload"]["ciphertext"]),
                saved_at=str(document.get("saved_at", "")),
            )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise Corrupt() from exc

    @classmethod
    def read(cls, path: Path) -> "Envelope":
        return cls.from_bytes(path.read_bytes())

    def write(self, path: Path) -> None:
        write_atomic(path, self.to_bytes())


def write_atomic(path: Path, data: bytes) -> None:
    """Writes to a temporary file in the same folder, flushes it to disk and
    renames it over the target: a crash leaves either the old or the new
    vault, never half of one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        if hasattr(os, "fchmod"):  # not available on Windows
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise Invalid(f"The password needs at least {MIN_PASSWORD_LENGTH} characters")
