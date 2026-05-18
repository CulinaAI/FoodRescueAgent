import os
from fastapi import Header, HTTPException


_API_KEY = os.getenv("FOOD_RESCUE_API_KEY", "")


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    if not _API_KEY or x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
