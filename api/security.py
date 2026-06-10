import hmac
import os
from fastapi import Header, HTTPException


_API_KEY = os.getenv("FOOD_RESCUE_API_KEY", "")


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    # Constant-time comparison to avoid leaking the key via response timing (CWE-208).
    # Empty server key still fails closed (no key configured → reject all).
    if not _API_KEY or not hmac.compare_digest(x_api_key, _API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")
