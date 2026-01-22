from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from fastapi import HTTPException


def _jwt_secret() -> str:
    secret = (os.getenv("JWT_SECRET", "") or "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="JWT not configured")
    return secret


def _jwt_issuer() -> str:
    return (os.getenv("JWT_ISSUER", "globalcart") or "globalcart").strip()


def _jwt_audience() -> str:
    return (os.getenv("JWT_AUDIENCE", "globalcart") or "globalcart").strip()


def _jwt_ttl_minutes() -> int:
    try:
        return int(os.getenv("JWT_TTL_MINUTES", "120"))
    except ValueError:
        return 120


def create_access_token(*, subject: str, role: str, extra: Optional[Dict[str, Any]] = None) -> str:
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iss": _jwt_issuer(),
        "aud": _jwt_audience(),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=_jwt_ttl_minutes())).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(
            token,
            _jwt_secret(),
            algorithms=["HS256"],
            audience=_jwt_audience(),
            issuer=_jwt_issuer(),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def parse_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts[0].strip().lower(), parts[1].strip()
    if scheme != "bearer" or not token:
        return None
    return token


def require_admin_from_token_payload(payload: Dict[str, Any]) -> None:
    role = str(payload.get("role") or "")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
