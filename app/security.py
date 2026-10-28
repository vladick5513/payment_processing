import secrets
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.settings import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Annotated[str | None, Security(api_key_header)]) -> None:
    if api_key is None or not secrets.compare_digest(api_key.encode(), settings.API_KEY.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
