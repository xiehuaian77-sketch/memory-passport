"""Web3 wallet authentication & SIWE verification service.

Provides:
- Strict EIP-55 address normalization and validation
- EIP-4361 (SIWE) standard challenge message construction
- Thread-safe, bounded in-process single-use NonceStore with 5-minute TTL
- Signature recovery and verification via eth-account
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import secrets
import threading

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import is_address, to_checksum_address

logger = logging.getLogger("memory_passport.wallet")

DEFAULT_STATEMENT = "Sign in to Memory Passport to verify ownership of your AI Agent long-term memories."
DEFAULT_CHAIN_ID = 10143  # Monad Testnet
NONCE_TTL_SECONDS = 300   # 5 minutes
MAX_NONCE_STORE_SIZE = 10000


def normalize_address(address: str | None) -> str:
    """Normalize and validate an Ethereum / EVM address to EIP-55 checksum format.

    Raises:
        ValueError: If address is missing, non-string, or invalid hex format.
    """
    if not address or not isinstance(address, str):
        raise ValueError("Address must be a non-empty string")

    cleaned = address.strip()
    if not is_address(cleaned):
        raise ValueError("Invalid Ethereum address format")

    try:
        return to_checksum_address(cleaned)
    except Exception as e:
        raise ValueError(f"Failed to normalize Ethereum address: {e}") from e


def format_iso_utc(dt: datetime) -> str:
    """Format datetime as UTC ISO 8601 with trailing 'Z'."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_siwe_message(
    domain: str,
    address: str,
    statement: str,
    uri: str,
    chain_id: int,
    nonce: str,
    issued_at: str,
    expires_at: str,
) -> str:
    """Construct an EIP-4361 (SIWE) compliant message string."""
    lines = [
        f"{domain} wants you to sign in with your Ethereum account:",
        address,
        "",
        statement,
        "",
        f"URI: {uri}",
        "Version: 1",
        f"Chain ID: {chain_id}",
        f"Nonce: {nonce}",
        f"Issued At: {issued_at}",
        f"Expiration Time: {expires_at}",
    ]
    return "\n".join(lines)


@dataclass(frozen=True)
class NonceRecord:
    """In-memory record storing nonce challenge details."""

    nonce: str
    normalized_address: str
    domain: str
    uri: str
    chain_id: int
    statement: str
    issued_at: datetime
    expires_at: datetime
    message: str


class NonceStore:
    """Bounded, thread-safe, single-use in-memory TTL nonce store.

    Note:
        Designed for local / demo single-process operation.
        In multi-worker production deployments, this should be backed by
        Redis or a shared distributed key-value store.
    """

    def __init__(self, ttl_seconds: int = NONCE_TTL_SECONDS, max_size: int = MAX_NONCE_STORE_SIZE) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_size = max_size
        self._store: dict[str, NonceRecord] = {}
        self._lock = threading.Lock()

    def _prune_expired_locked(self, now: datetime) -> None:
        """Remove expired entries (caller must hold _lock)."""
        expired_keys = [k for k, rec in self._store.items() if now >= rec.expires_at]
        for k in expired_keys:
            del self._store[k]

    def create_nonce(
        self,
        normalized_address: str,
        domain: str,
        uri: str,
        chain_id: int = DEFAULT_CHAIN_ID,
        statement: str = DEFAULT_STATEMENT,
    ) -> NonceRecord:
        """Generate a cryptographically secure, single-use nonce challenge."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=self._ttl_seconds)
        nonce = secrets.token_urlsafe(16)

        issued_at_str = format_iso_utc(now)
        expires_at_str = format_iso_utc(expires)

        message = build_siwe_message(
            domain=domain,
            address=normalized_address,
            statement=statement,
            uri=uri,
            chain_id=chain_id,
            nonce=nonce,
            issued_at=issued_at_str,
            expires_at=expires_at_str,
        )

        record = NonceRecord(
            nonce=nonce,
            normalized_address=normalized_address,
            domain=domain,
            uri=uri,
            chain_id=chain_id,
            statement=statement,
            issued_at=now,
            expires_at=expires,
            message=message,
        )

        with self._lock:
            self._prune_expired_locked(now)
            if len(self._store) >= self._max_size:
                # Discard oldest to prevent unbounded memory growth
                oldest_key = min(self._store.keys(), key=lambda k: self._store[k].issued_at)
                del self._store[oldest_key]
            self._store[nonce] = record

        return record

    def consume_nonce(self, nonce: str, normalized_address: str) -> NonceRecord:
        """Retrieve and immediately burn a nonce.

        Raises:
            ValueError: If nonce not found, expired, or claimed by different address.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            if nonce not in self._store:
                self._prune_expired_locked(now)
                raise ValueError("Nonce not found or already consumed")

            record = self._store[nonce]

            # Enforce expiration
            if now >= record.expires_at:
                del self._store[nonce]
                self._prune_expired_locked(now)
                raise ValueError("Nonce has expired")

            # Enforce address binding
            if record.normalized_address.lower() != normalized_address.lower():
                del self._store[nonce]  # Burn to mitigate probe/replay attacks
                self._prune_expired_locked(now)
                raise ValueError("Nonce does not match requested wallet address")

            # Single-use consumption
            del self._store[nonce]
            self._prune_expired_locked(now)
            return record

    def clear(self) -> None:
        """Clear all stored nonces (primarily for test cleanup)."""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


# Global singleton instance
nonce_store = NonceStore()


def verify_wallet_signature(
    address: str,
    signature: str,
    nonce: str,
) -> NonceRecord:
    """Verify an EVM wallet signature against the stored SIWE message.

    Steps:
    1. Normalize target address
    2. Check signature format
    3. Consume nonce (validating TTL and address match)
    4. Recover signer address via eth-account ecrecover
    5. Compare recovered address to requested address

    Raises:
        ValueError: If address, signature, or recovery fails.
    """
    norm_address = normalize_address(address)

    if not signature or not isinstance(signature, str):
        raise ValueError("Signature must be a non-empty string")

    clean_sig = signature.strip()
    if not (clean_sig.startswith("0x") or len(clean_sig) in (130, 132)):
        raise ValueError("Malformed signature format")

    # Step 3: Consume nonce (atomic check & delete)
    record = nonce_store.consume_nonce(nonce, norm_address)

    # Step 4: Recover address from SIWE message
    try:
        signable_message = encode_defunct(text=record.message)
        recovered_raw = Account.recover_message(signable_message, signature=clean_sig)
        recovered_address = normalize_address(recovered_raw)
    except Exception as e:
        logger.warning("Failed to recover signer from signature: %s", type(e).__name__)
        raise ValueError("Invalid signature or recovery failed") from e

    # Step 5: Equality check
    if recovered_address.lower() != norm_address.lower():
        raise ValueError(f"Signature mismatch: recovered {recovered_address} != expected {norm_address}")

    return record
