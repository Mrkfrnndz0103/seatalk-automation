import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class SeaTalkSystemAccountClient:
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url.strip()

    @property
    def enabled(self) -> bool:
        return bool(self._webhook_url)

    async def send_text_message(
        self,
        content: str,
        *,
        at_all: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tag": "text",
            "text": {
                "content": content,
            },
        }
        if at_all:
            payload["text"]["at_all"] = True

        return await self._post(payload)

    async def send_image_message(self, image_base64: str) -> dict[str, Any]:
        primary_payload: dict[str, Any] = {
            "tag": "image",
            "image_base64": {
                "content": image_base64,
            },
        }
        try:
            return await self._post(primary_payload)
        except Exception:
            # Some webhook variants accept `image` instead of `image_base64`.
            fallback_payload: dict[str, Any] = {
                "tag": "image",
                "image": {
                    "content": image_base64,
                },
            }
            return await self._post(fallback_payload)

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("system account webhook URL is not configured")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                self._webhook_url,
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        if isinstance(data, dict) and data.get("code", 0) not in (0, None):
            logger.error("system account webhook send failed: %s", data)
            raise RuntimeError(f"failed to send system account message, code={data.get('code')}")

        return data if isinstance(data, dict) else {"ok": True}
