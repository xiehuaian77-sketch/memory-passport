"""Auth router — email registration, JWT login, and Web3 wallet SIWE authentication."""

from datetime import datetime, timedelta, timezone
import logging

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.user import TokenResponse, UserLogin, UserOut, UserRegister, UserUpdate
from app.schemas.wallet import WalletAuthResponse, WalletNonceResponse, WalletVerifyRequest
from app.services import wallet_service

logger = logging.getLogger("memory_passport.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode("utf-8")[:72]
    return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))


def _create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user with email + password."""
    # Check duplicate email
    stmt = select(User).where(User.email == body.email)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    token = _create_token(user.id)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login with email + password, returns JWT."""
    stmt = select(User).where(User.email == body.email)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = _create_token(user.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UserUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile."""
    if body.display_name is not None:
        user.display_name = body.display_name
    await db.flush()
    await db.refresh(user)
    return user


# ---------- Web3 Wallet SIWE Endpoints ----------


@router.get("/wallet/nonce", response_model=WalletNonceResponse)
async def get_wallet_nonce(
    request: Request,
    address: str = Query(..., description="EVM wallet address (0x...)"),
    chain_id: int = Query(default=wallet_service.DEFAULT_CHAIN_ID, description="EVM Chain ID (default 10143 Monad)"),
):
    """Generate a single-use cryptographic SIWE challenge for wallet authentication."""
    try:
        norm_address = wallet_service.normalize_address(address)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    # Derive host/domain and URI from request context or configured origins
    host = request.headers.get("host")
    if not host and settings.cors_origin_list:
        host = settings.cors_origin_list[0].replace("http://", "").replace("https://", "")
    if not host:
        host = "localhost:3000"

    domain = host
    scheme = request.url.scheme or "http"
    uri = f"{scheme}://{host}"

    record = wallet_service.nonce_store.create_nonce(
        normalized_address=norm_address,
        domain=domain,
        uri=uri,
        chain_id=chain_id,
    )

    return WalletNonceResponse(
        nonce=record.nonce,
        domain=record.domain,
        statement=record.statement,
        uri=record.uri,
        chain_id=record.chain_id,
        issued_at=wallet_service.format_iso_utc(record.issued_at),
        expires_at=wallet_service.format_iso_utc(record.expires_at),
        message=record.message,
    )


@router.post("/wallet/verify", response_model=WalletAuthResponse)
async def verify_wallet(
    body: WalletVerifyRequest,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None, description="Optional Bearer token for binding"),
):
    """Verify SIWE signature and bind wallet or login."""
    # 1. Resolve optional authenticated user if Bearer token present
    current_user: User | None = None
    if authorization:
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format. Use: Bearer <token>",
            )
        token_str = authorization.removeprefix("Bearer ").strip()
        try:
            payload = jwt.decode(
                token_str,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            user_id: str | None = payload.get("sub")
            exp: float | None = payload.get("exp")
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token payload missing 'sub'",
                )
            if exp is not None and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has expired",
                )
            stmt_me = select(User).where(User.id == user_id)
            current_user = (await db.execute(stmt_me)).scalar_one_or_none()
            if current_user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authenticated user not found",
                )
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e}",
            ) from e

    # 2. Cryptographic signature verification
    try:
        record = wallet_service.verify_wallet_signature(
            address=body.address,
            signature=body.signature,
            nonce=body.nonce,
        )
    except ValueError as e:
        err_msg = str(e)
        err_lower = err_msg.lower()
        if any(k in err_lower for k in ["expired", "match", "not found", "consumed", "recovery", "invalid signature"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err_msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg) from e

    norm_address = record.normalized_address

    # 3. Account binding or login routing
    if current_user is not None:
        # Case A: Authenticated user binding wallet
        if current_user.wallet_address:
            if current_user.wallet_address.lower() == norm_address.lower():
                token = _create_token(current_user.id)
                return WalletAuthResponse(
                    access_token=token,
                    user=UserOut.model_validate(current_user),
                    action="bound",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Current user is already bound to a different wallet address ({current_user.wallet_address})",
            )

        # Check if wallet is already bound to another user
        stmt_existing = select(User).where(User.wallet_address == norm_address)
        existing_user = (await db.execute(stmt_existing)).scalar_one_or_none()
        if existing_user is not None and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This wallet address is already bound to another user account",
            )

        # Apply binding
        current_user.wallet_address = norm_address
        current_user.wallet_bound_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(current_user)

        token = _create_token(current_user.id)
        masked = f"{norm_address[:6]}...{norm_address[-4:]}"
        logger.info("Successfully bound wallet %s to user %s", masked, current_user.id)

        return WalletAuthResponse(
            access_token=token,
            user=UserOut.model_validate(current_user),
            action="bound",
        )

    # Case B: Unauthenticated request (wallet login)
    stmt_user = select(User).where(User.wallet_address == norm_address)
    bound_user = (await db.execute(stmt_user)).scalar_one_or_none()
    if bound_user is not None:
        token = _create_token(bound_user.id)
        masked = f"{norm_address[:6]}...{norm_address[-4:]}"
        logger.info("Wallet login successful for user %s with wallet %s", bound_user.id, masked)
        return WalletAuthResponse(
            access_token=token,
            user=UserOut.model_validate(bound_user),
            action="login",
        )

    # Unbound wallet cannot self-register without email/password under current schema
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Wallet address is not associated with any account. Please login with email first and bind this wallet in Identity Settings.",
    )
