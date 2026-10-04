"""Cryptographic primitives: Argon2id key derivation, AES-256-GCM sealing and
recovery key encoding. Nothing in this module touches the disk."""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import WrongRecoveryKey

KEY_LEN = 32
NONCE_LEN = 12
SALT_LEN = 16


@dataclass(frozen=True)
class KdfParams:
    """Argon2id cost. Stored in the vault header, so a vault keeps opening even
    if the defaults change later."""

    memory_kib: int = 64 * 1024  # 64 MiB, about half a second per unlock
    time_cost: int = 3
    parallelism: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "KdfParams":
        return cls(int(data["memory_kib"]), int(data["time_cost"]), int(data["parallelism"]))


# Cheap parameters, for tests only.
TEST_KDF = KdfParams(memory_kib=8, time_cost=1, parallelism=1)


def random_bytes(n: int) -> bytes:
    return secrets.token_bytes(n)


def random_key() -> bytearray:
    return bytearray(secrets.token_bytes(KEY_LEN))


def derive_key(secret: bytes, salt: bytes, params: KdfParams) -> bytearray:
    return bytearray(
        hash_secret_raw(
            secret=secret,
            salt=salt,
            time_cost=params.time_cost,
            memory_cost=params.memory_kib,
            parallelism=params.parallelism,
            hash_len=KEY_LEN,
            type=Type.ID,
        )
    )


def seal(key: bytes | bytearray, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes]:
    """Encrypts with a fresh random nonce. ``aad`` is authenticated but not
    encrypted: it binds the ciphertext to the place it belongs to."""
    nonce = random_bytes(NONCE_LEN)
    return nonce, AESGCM(bytes(key)).encrypt(nonce, plaintext, aad)


def open_sealed(key: bytes | bytearray, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes | None:
    """Returns ``None`` when the key is wrong or the data was tampered with:
    GCM cannot tell the two apart, and callers should not either."""
    if len(nonce) != NONCE_LEN:
        return None
    try:
        return AESGCM(bytes(key)).decrypt(nonce, ciphertext, aad)
    except InvalidTag:
        return None


def wipe(buffer: bytearray | None) -> None:
    """Best effort: Python may still hold copies elsewhere in memory."""
    if buffer is not None:
        for i in range(len(buffer)):
            buffer[i] = 0


# Crockford base32: no I, L, O or U, so a key survives being copied by hand.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
RECOVERY_BYTES = 20  # 160 bits -> 32 characters


def new_recovery_key() -> str:
    """Eight groups of four characters, e.g. ``7KQ2-...``."""
    value = int.from_bytes(random_bytes(RECOVERY_BYTES), "big")
    chars = []
    for _ in range(32):
        chars.append(ALPHABET[value & 31])
        value >>= 5
    raw = "".join(reversed(chars))
    return "-".join(raw[i : i + 4] for i in range(0, 32, 4))


def normalize_recovery_key(text: str) -> str:
    """Canonical form used for key derivation: upper case, no separators, and
    look-alike letters folded the way Crockford base32 specifies."""
    out = []
    for c in text.upper():
        if c in "- \t\r\n":
            continue
        c = {"O": "0", "I": "1", "L": "1"}.get(c, c)
        if c not in ALPHABET:
            raise WrongRecoveryKey()
        out.append(c)
    if len(out) != 32:
        raise WrongRecoveryKey()
    return "".join(out)
