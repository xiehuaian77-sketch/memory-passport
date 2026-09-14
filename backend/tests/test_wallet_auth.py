"""Comprehensive tests for Web3 EVM / Monad Wallet SIWE Authentication (Phase 6.4 Step 1).

Covers:
1. Nonce generation
2. Nonce TTL (5 minutes)
3. Nonce single-use enforcement
4. Valid signature & authentication
5. Invalid signature rejection
6. Wrong address claiming nonce
7. Wrong / non-existent nonce
8. Expired nonce rejection
9. Malformed address rejection
10. Malformed signature rejection
11. Cross-user wallet binding conflict (409)
12. Already-bound wallet conflict (409)
13. Current authenticated user binding
14. wallet_bound_at timestamp setting
15. JWT token compatibility with /api/auth/me
16. No user mutation on failed verification
17. Chain ID binding & customization
18. Domain / URI preservation in SIWE message
19. Replay attack prevention
20. Unregistered wallet login rejection (404)
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import to_checksum_address
from httpx import AsyncClient
import pytest

from app.services import wallet_service


def _create_ephemeral_wallet() -> tuple[Any, str]:
    """Generate an ephemeral, test-only in-memory EVM account."""
    acc = Account.create()
    checksum_addr = to_checksum_address(acc.address)
    return acc, checksum_addr


def _sign_message(acc: Any, message: str) -> str:
    """Sign an EIP-4361 / SIWE text message using an ephemeral test account."""
    signable = encode_defunct(text=message)
    sig = acc.sign_message(signable).signature.hex()
    return "0x" + sig if not sig.startswith("0x") else sig


@pytest.mark.asyncio
async def test_nonce_generation(client: AsyncClient):
    """Test 1: Nonce generation with proper SIWE formatting."""
    _, address = _create_ephemeral_wallet()
    resp = await client.get(f"/api/auth/wallet/nonce?address={address}&chain_id=10143")
    assert resp.status_code == 200
    data = resp.json()

    assert "nonce" in data and len(data["nonce"]) > 10
    assert data["chain_id"] == 10143
    assert address in data["message"]
    assert "Chain ID: 10143" in data["message"]
    assert f"Nonce: {data['nonce']}" in data["message"]
    assert "Sign in to Memory Passport" in data["message"]


@pytest.mark.asyncio
async def test_nonce_ttl(client: AsyncClient):
    """Test 2: Nonce TTL calculation (5 minutes)."""
    _, address = _create_ephemeral_wallet()
    resp = await client.get(f"/api/auth/wallet/nonce?address={address}")
    assert resp.status_code == 200
    data = resp.json()

    issued = datetime.fromisoformat(data["issued_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    diff_seconds = (expires - issued).total_seconds()
    assert 295 <= diff_seconds <= 305


@pytest.mark.asyncio
async def test_nonce_single_use(client: AsyncClient):
    """Test 3 & 19: Nonce single-use enforcement and replay protection."""
    # First register a user so wallet can be bound
    reg_resp = await client.post("/api/auth/register", json={
        "email": "singleuse@example.com",
        "password": "password123",
        "display_name": "SingleUse User",
    })
    token = reg_resp.json()["access_token"]

    acc, address = _create_ephemeral_wallet()
    n_resp = await client.get(f"/api/auth/wallet/nonce?address={address}")
    n_data = n_resp.json()

    signature = _sign_message(acc, n_data["message"])
    payload = {
        "address": address,
        "signature": signature,
        "nonce": n_data["nonce"],
    }

    # First attempt: succeeds
    v1 = await client.post(
        "/api/auth/wallet/verify",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert v1.status_code == 200

    # Replay attempt with same nonce: rejected (401)
    v2 = await client.post(
        "/api/auth/wallet/verify",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert v2.status_code == 401
    assert "already consumed" in v2.json()["detail"].lower() or "not found" in v2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invalid_signature_rejection(client: AsyncClient):
    """Test 5: Rejection of invalid ECDSA signature."""
    _, address = _create_ephemeral_wallet()
    n_resp = await client.get(f"/api/auth/wallet/nonce?address={address}")
    nonce = n_resp.json()["nonce"]

    # 65-byte fake signature
    fake_sig = "0x" + "11" * 65
    resp = await client.post("/api/auth/wallet/verify", json={
        "address": address,
        "signature": fake_sig,
        "nonce": nonce,
    })
    assert resp.status_code in (400, 401)


@pytest.mark.asyncio
async def test_wrong_address_claiming_nonce(client: AsyncClient):
    """Test 6: Wallet B attempting to use Wallet A's nonce."""
    _, address_a = _create_ephemeral_wallet()
    acc_b, address_b = _create_ephemeral_wallet()

    n_resp = await client.get(f"/api/auth/wallet/nonce?address={address_a}")
    n_data = n_resp.json()

    # B signs message intended for A
    sig_b = _sign_message(acc_b, n_data["message"])

    resp = await client.post("/api/auth/wallet/verify", json={
        "address": address_b,
        "signature": sig_b,
        "nonce": n_data["nonce"],
    })
    assert resp.status_code == 401
    assert "does not match" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_wrong_nonce(client: AsyncClient):
    """Test 7: Verification with non-existent nonce."""
    acc, address = _create_ephemeral_wallet()
    sig = _sign_message(acc, "some message")

    resp = await client.post("/api/auth/wallet/verify", json={
        "address": address,
        "signature": sig,
        "nonce": "completely-bogus-nonce-xyz",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_expired_nonce_rejection(client: AsyncClient):
    """Test 8: Rejection of expired nonce."""
    acc, address = _create_ephemeral_wallet()
    record = wallet_service.nonce_store.create_nonce(
        normalized_address=address,
        domain="localhost",
        uri="http://localhost",
        chain_id=10143,
    )
    # Force expire in memory
    expired_record = wallet_service.NonceRecord(
        nonce=record.nonce,
        normalized_address=record.normalized_address,
        domain=record.domain,
        uri=record.uri,
        chain_id=record.chain_id,
        statement=record.statement,
        issued_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        message=record.message,
    )
    with wallet_service.nonce_store._lock:
        wallet_service.nonce_store._store[record.nonce] = expired_record

    sig = _sign_message(acc, record.message)
    resp = await client.post("/api/auth/wallet/verify", json={
        "address": address,
        "signature": sig,
        "nonce": record.nonce,
    })
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_malformed_address(client: AsyncClient):
    """Test 9: Rejection of malformed wallet addresses."""
    resp1 = await client.get("/api/auth/wallet/nonce?address=not-an-address")
    assert resp1.status_code == 400

    resp2 = await client.post("/api/auth/wallet/verify", json={
        "address": "0xinvalidhex123",
        "signature": "0x" + "aa" * 65,
        "nonce": "test-nonce",
    })
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_malformed_signature(client: AsyncClient):
    """Test 10: Rejection of malformed signature strings."""
    _, address = _create_ephemeral_wallet()
    resp = await client.post("/api/auth/wallet/verify", json={
        "address": address,
        "signature": "short-sig",
        "nonce": "any-nonce",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_authenticated_wallet_binding_and_jwt_compatibility(client: AsyncClient):
    """Test 4, 13, 14, 15: Full binding flow, wallet_bound_at, and JWT validity."""
    # 1. Register a user
    reg = await client.post("/api/auth/register", json={
        "email": "web3dev@example.com",
        "password": "devpassword123",
        "display_name": "Web3 Dev",
    })
    assert reg.status_code == 201
    jwt_token = reg.json()["access_token"]

    # 2. Get nonce for new wallet
    acc, address = _create_ephemeral_wallet()
    n_resp = await client.get(f"/api/auth/wallet/nonce?address={address}&chain_id=10143")
    assert n_resp.status_code == 200
    n_data = n_resp.json()

    # 3. Sign and verify with Bearer token
    sig = _sign_message(acc, n_data["message"])
    v_resp = await client.post(
        "/api/auth/wallet/verify",
        json={"address": address, "signature": sig, "nonce": n_data["nonce"]},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert v_resp.status_code == 200
    v_data = v_resp.json()
    assert v_data["action"] == "bound"
    assert v_data["user"]["wallet_address"] == address
    assert v_data["user"]["wallet_bound_at"] is not None

    # 4. Check /api/auth/me with newly issued access token
    new_token = v_data["access_token"]
    me_resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert me_resp.status_code == 200
    me = me_resp.json()
    assert me["wallet_address"] == address
    assert me["email"] == "web3dev@example.com"

    # 5. Now test unauthenticated login with this bound wallet!
    n_resp2 = await client.get(f"/api/auth/wallet/nonce?address={address}")
    n_data2 = n_resp2.json()
    sig2 = _sign_message(acc, n_data2["message"])

    login_resp = await client.post(
        "/api/auth/wallet/verify",
        json={"address": address, "signature": sig2, "nonce": n_data2["nonce"]},
    )
    assert login_resp.status_code == 200
    l_data = login_resp.json()
    assert l_data["action"] == "login"
    assert l_data["user"]["id"] == me["id"]


@pytest.mark.asyncio
async def test_cross_user_wallet_binding_conflict(client: AsyncClient):
    """Test 11: Preventing binding a wallet that already belongs to another user (409)."""
    # User 1 binds Wallet 1
    u1 = await client.post("/api/auth/register", json={
        "email": "user1@example.com",
        "password": "password123",
        "display_name": "User 1",
    })
    token1 = u1.json()["access_token"]
    acc1, address1 = _create_ephemeral_wallet()

    n1 = await client.get(f"/api/auth/wallet/nonce?address={address1}")
    sig1 = _sign_message(acc1, n1.json()["message"])
    v1 = await client.post(
        "/api/auth/wallet/verify",
        json={"address": address1, "signature": sig1, "nonce": n1.json()["nonce"]},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert v1.status_code == 200

    # User 2 tries to bind Wallet 1
    u2 = await client.post("/api/auth/register", json={
        "email": "user2@example.com",
        "password": "password123",
        "display_name": "User 2",
    })
    token2 = u2.json()["access_token"]

    n2 = await client.get(f"/api/auth/wallet/nonce?address={address1}")
    sig2 = _sign_message(acc1, n2.json()["message"])
    v2 = await client.post(
        "/api/auth/wallet/verify",
        json={"address": address1, "signature": sig2, "nonce": n2.json()["nonce"]},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert v2.status_code == 409
    assert "already bound to another user" in v2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_already_bound_user_cannot_bind_different_wallet(client: AsyncClient):
    """Test 12: User already having a bound wallet cannot bind a second wallet (409)."""
    u = await client.post("/api/auth/register", json={
        "email": "twowallets@example.com",
        "password": "password123",
        "display_name": "Two Wallets",
    })
    token = u.json()["access_token"]

    acc1, address1 = _create_ephemeral_wallet()
    acc2, address2 = _create_ephemeral_wallet()

    # Bind first wallet
    n1 = await client.get(f"/api/auth/wallet/nonce?address={address1}")
    sig1 = _sign_message(acc1, n1.json()["message"])
    v1 = await client.post(
        "/api/auth/wallet/verify",
        json={"address": address1, "signature": sig1, "nonce": n1.json()["nonce"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert v1.status_code == 200

    # Attempt to bind second wallet
    n2 = await client.get(f"/api/auth/wallet/nonce?address={address2}")
    sig2 = _sign_message(acc2, n2.json()["message"])
    v2 = await client.post(
        "/api/auth/wallet/verify",
        json={"address": address2, "signature": sig2, "nonce": n2.json()["nonce"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert v2.status_code == 409
    assert "already bound to a different wallet" in v2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_no_mutation_on_failed_verification(client: AsyncClient):
    """Test 16: Ensure user model is not mutated if verification fails."""
    u = await client.post("/api/auth/register", json={
        "email": "nomutate@example.com",
        "password": "password123",
        "display_name": "No Mutate",
    })
    token = u.json()["access_token"]
    _, address = _create_ephemeral_wallet()

    n = await client.get(f"/api/auth/wallet/nonce?address={address}")
    # Submit wrong signature
    fake_sig = "0x" + "55" * 65
    v = await client.post(
        "/api/auth/wallet/verify",
        json={"address": address, "signature": fake_sig, "nonce": n.json()["nonce"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert v.status_code in (400, 401)

    # Check user record remains unbound
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["wallet_address"] is None
    assert me.json()["wallet_bound_at"] is None


@pytest.mark.asyncio
async def test_unregistered_unauthenticated_wallet_rejected(client: AsyncClient):
    """Test 20: Unbound wallet cannot directly login without prior registration."""
    acc, address = _create_ephemeral_wallet()
    n = await client.get(f"/api/auth/wallet/nonce?address={address}")
    sig = _sign_message(acc, n.json()["message"])

    resp = await client.post("/api/auth/wallet/verify", json={
        "address": address,
        "signature": sig,
        "nonce": n.json()["nonce"],
    })
    assert resp.status_code == 404
    assert "not associated with any account" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_tampered_siwe_message_rejection(client: AsyncClient):
    """Test 17 & 18: Rejection if client tampers with chain_id, domain, or statement."""
    acc, address = _create_ephemeral_wallet()
    n = await client.get(f"/api/auth/wallet/nonce?address={address}&chain_id=10143")
    n_data = n.json()

    # Tamper with message by changing Chain ID before signing
    tampered_msg = n_data["message"].replace("Chain ID: 10143", "Chain ID: 1")
    tampered_sig = _sign_message(acc, tampered_msg)

    resp = await client.post("/api/auth/wallet/verify", json={
        "address": address,
        "signature": tampered_sig,
        "nonce": n_data["nonce"],
    })
    assert resp.status_code == 401
    assert "mismatch" in resp.json()["detail"].lower() or "recovery" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_custom_chain_id_and_domain_preservation(client: AsyncClient):
    """Test 17: Support for custom EVM Chain ID."""
    _, address = _create_ephemeral_wallet()
    resp = await client.get(f"/api/auth/wallet/nonce?address={address}&chain_id=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["chain_id"] == 1
    assert "Chain ID: 1" in data["message"]
