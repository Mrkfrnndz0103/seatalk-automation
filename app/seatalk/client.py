import asyncio
import logging
import time
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class SeaTalkClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token: str | None = None
        self._token_expire_ts = 0.0
        self._lock = asyncio.Lock()

    async def _refresh_token(self) -> None:
        url = f"{self._settings.seatalk_api_base_url}/auth/app_access_token"
        payload = {
            "app_id": self._settings.seatalk_app_id,
            "app_secret": self._settings.seatalk_app_secret,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        code = data.get("code")
        if code != 0:
            raise RuntimeError(f"failed to obtain app access token, code={code}, payload={data}")

        self._token = data["app_access_token"]
        # API returns unix timestamp in seconds.
        expire_ts = float(data["expire"])
        self._token_expire_ts = max(expire_ts - 60.0, time.time() + 30.0)

    async def get_token(self) -> str:
        async with self._lock:
            now = time.time()
            if self._token and now < self._token_expire_ts:
                return self._token
            await self._refresh_token()
            return self._token or ""

    async def send_text_message(
        self,
        employee_code: str,
        content: str,
        *,
        thread_id: str | None = None,
        usable_platform: str = "all",
    ) -> dict[str, Any]:
        token = await self.get_token()
        url = f"{self._settings.seatalk_api_base_url}/messaging/v2/single_chat"

        payload: dict[str, Any] = {
            "employee_code": employee_code,
            "message": {
                "tag": "text",
                "text": {
                    "format": 1,
                    "content": content,
                },
            },
            "usable_platform": usable_platform,
        }
        if thread_id:
            payload["thread_id"] = thread_id

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        if data.get("code") != 0:
            logger.error("send_message failed with response: %s", data)
            raise RuntimeError(f"failed to send message, code={data.get('code')}")

        return data