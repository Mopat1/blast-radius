"""Authentication for BlastRadius Cloud: pbkdf2 password hashing + JWT."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import secrets

from dotenv import load_dotenv
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .db import User, get_db

# Load environment variables from .env (for local development)
load_dotenv()

# ---------------------------------------------------------------------
# JWT Configuration
# ---------------------------------------------------------------------

ENV = os.getenv("ENV", "development")

# Read JWT signing secret from environment
SECRET = os.getenv("BLASTRADIUS_SECRET")

# In production, a secret is mandatory
if ENV == "production" and not SECRET:
    raise RuntimeError(
        "BLASTRADIUS_SECRET environment variable must be set in production."
    )

# In local development, generate a temporary secret if none exists
if SECRET is None:
    SECRET = secrets.token_hex(64)

ALGO = "HS256"
TOKEN_TTL_HOURS = 24

# HTTP Bearer authentication
_bearer = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------
# Password Hashing
# ---------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt.encode(),
        200_000,
    )
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest_hex = stored.split("$", 1)
    except ValueError:
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt.encode(),
        200_000,
    )

    return hmac.compare_digest(digest.hex(), digest_hex)


# ---------------------------------------------------------------------
# JWT Tokens
# ---------------------------------------------------------------------

def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "exp": dt.datetime.utcnow() + dt.timedelta(hours=TOKEN_TTL_HOURS),
    }

    return jwt.encode(payload, SECRET, algorithm=ALGO)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing bearer token",
        )

    try:
        payload = jwt.decode(
            creds.credentials,
            SECRET,
            algorithms=[ALGO],
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired token",
        )

    user = db.get(User, int(payload["sub"]))

    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "User no longer exists",
        )

    return user