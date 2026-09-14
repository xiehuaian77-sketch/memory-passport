"""Schemas for Web3 wallet authentication and SIWE."""

from pydantic import BaseModel, Field

from app.schemas.user import UserOut


class WalletNonceResponse(BaseModel):
    """Response containing SIWE challenge and nonce."""

    nonce: str
    domain: str
    statement: str
    uri: str
    chain_id: int
    issued_at: str
    expires_at: str
    message: str


class WalletVerifyRequest(BaseModel):
    """Request payload for verifying a wallet signature."""

    address: str = Field(..., description="EVM wallet address (0x...)")
    signature: str = Field(..., description="Hex-encoded ECDSA signature (0x...)")
    nonce: str = Field(..., description="Nonce received from /wallet/nonce")


class WalletAuthResponse(BaseModel):
    """Response on successful wallet binding or login."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut
    action: str = Field(..., description="'bound' or 'login'")
