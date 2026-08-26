"""Where the provider credential lives, and what "encrypted" actually buys.

ADR-012 moved the API key from an environment variable into runtime state, and
that decision has a price this module pays in three places:

1. **The value never comes back out through the API.** `Vault.hint` is what a
   caller gets — the last four characters, nothing else — and there is no method
   here that returns a stored secret to anything but the provider client.
2. **It is encrypted at rest with a key from the environment.** Be precise about
   the guarantee: this protects against a *database dump*. It does not protect
   against someone who already has the `.env`, because that is where the key is.
   Writing "encrypted" without that sentence would be selling a guarantee that
   does not exist.
3. **A missing encryption key is a refusal, not a fallback.** Storing the secret
   in the clear "just for now" is exactly how a demo ends up in production with a
   plaintext credentials table.

The split between `Vault` and the store is deliberate: everything cryptographic
here is pure and testable without a container, and the Postgres half deals only
with bytes it cannot read.
"""

import json
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

HINT_LENGTH = 4


class CredentialsUnavailable(RuntimeError):
    """No encryption key configured — writing a secret is refused, never downgraded."""


class CredentialsCorrupted(RuntimeError):
    """The stored blob does not decrypt with the configured key.

    Almost always means the key was rotated or regenerated while credentials were
    already stored. Saying that out loud beats a stack trace from `cryptography`,
    because the fix is a person's decision: rotate back, or re-enter the keys.
    """


@dataclass(frozen=True)
class Vault:
    """Encrypts and decrypts the provider credential map. Knows nothing about storage."""

    key: str | None

    @property
    def usable(self) -> bool:
        return bool(self.key)

    def _fernet(self) -> Fernet:
        if not self.key:
            raise CredentialsUnavailable(
                "CONFIG_ENCRYPTION_KEY nao esta definida: guardar credencial em claro "
                "nao e uma opcao. Gere uma com Fernet.generate_key() e coloque no .env."
            )
        try:
            return Fernet(self.key)
        except (ValueError, TypeError) as invalid:
            raise CredentialsUnavailable(
                "CONFIG_ENCRYPTION_KEY nao e uma chave Fernet valida (base64 urlsafe de 32 bytes)"
            ) from invalid

    def seal(self, credentials: dict[str, str]) -> bytes:
        """Encrypt the whole `{provider: api_key}` map into one opaque blob."""
        return self._fernet().encrypt(json.dumps(credentials).encode("utf-8"))

    def open(self, blob: bytes | None) -> dict[str, str]:
        """Decrypt the blob. An empty store is an empty map, not an error."""
        if not blob:
            return {}
        try:
            plain = self._fernet().decrypt(blob)
        except InvalidToken as wrong_key:
            raise CredentialsCorrupted(
                "as credenciais guardadas nao abrem com a CONFIG_ENCRYPTION_KEY atual — "
                "a chave foi trocada? ou volte a chave anterior, ou grave as credenciais de novo."
            ) from wrong_key
        decoded: dict[str, str] = json.loads(plain)
        return decoded

    @staticmethod
    def hint(secret: str) -> str:
        """What the API is allowed to show: enough to recognise, useless to steal."""
        return f"…{secret[-HINT_LENGTH:]}" if len(secret) > HINT_LENGTH else "…"
