from typing import Any

import httpx

from app.webhook.exceptions import WebhookResponseError, WebhookTransportError


class WebhookClient:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def send(self, url: str, payload: dict[str, Any]) -> None:
        try:
            response = await self.http.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise WebhookTransportError(str(exc)) from exc
        if not response.is_success:
            raise WebhookResponseError(f"HTTP {response.status_code}")
