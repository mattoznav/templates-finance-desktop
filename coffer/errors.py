"""Errors returned to the interface.

The UI receives ``{"code": ..., "message": ...}`` and switches on ``code``, so
codes are part of the API and must stay stable.
"""


class CofferError(Exception):
    code = "error"
    default_message = "Something went wrong"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.default_message)
        self.message = message or self.default_message

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


class Locked(CofferError):
    code = "locked"
    default_message = "The vault is locked"


class NoVault(CofferError):
    code = "no_vault"
    default_message = "No vault exists yet"


class VaultExists(CofferError):
    code = "vault_exists"
    default_message = "A vault already exists on this device"


class WrongPassword(CofferError):
    code = "wrong_password"
    default_message = "Wrong password"


class WrongRecoveryKey(CofferError):
    code = "wrong_recovery_key"
    default_message = "Wrong recovery key"


class Corrupt(CofferError):
    code = "corrupt"
    default_message = "This file is not a Coffer vault, or it is damaged"


class Offline(CofferError):
    code = "offline"
    default_message = "Network access is disabled in offline mode"


class NotFound(CofferError):
    code = "not_found"
    default_message = "Not found"


class Invalid(CofferError):
    code = "invalid"
    default_message = "Invalid data"


class UnknownCommand(CofferError):
    code = "unknown_command"
