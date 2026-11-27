"""Клієнт REST API Комори (токен у X-Api-Key)."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from homeassistant.util.json import json_loads


class KomoraError(Exception):
    """Комора відповіла помилкою або недоступна."""


class KomoraAuthError(KomoraError):
    """Токен недійсний або відкликаний."""


def base_url(url: str) -> str:
    """Лише схема і хост: «https://komora.example.com/item/5» → «https://komora.example.com»."""
    parts = urlsplit(url.strip())
    return f"{parts.scheme}://{parts.netloc}"


class KomoraApi:
    def __init__(self, session: aiohttp.ClientSession, url: str, token: str) -> None:
        self._session = session
        self.url = base_url(url)
        self._headers = {"X-Api-Key": token, "Accept": "application/json"}

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self.url}/api{path}",
                json=json,
                params={k: v for k, v in (params or {}).items() if v is not None},
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                if r.status == 401:
                    raise KomoraAuthError("недійсний токен")
                text = await r.text()
                try:
                    body = json_loads(text) if text.strip() else None
                except ValueError:
                    # сторінка замість JSON: не та адреса або щось між HA і Комором
                    raise KomoraError(
                        f"відповідь не від API Комори (HTTP {r.status}, {r.content_type}) — перевір адресу"
                    ) from None
                if r.status >= 400:
                    msg = body.get("error") if isinstance(body, dict) else None
                    raise KomoraError(msg or text.strip()[:200] or f"HTTP {r.status}")
                return body
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise KomoraError(f"Комора недоступна: {e}") from e

    # --- читання
    async def health(self) -> dict:
        h = await self.request("GET", "/health")
        if not isinstance(h, dict) or h.get("status") != "ok":
            raise KomoraError("за цією адресою не Комора")
        return h

    async def features(self) -> dict:
        return await self.request("GET", "/features")

    async def units(self) -> list[dict]:
        return await self.request("GET", "/units")

    async def shopping(self, horizon: float) -> dict:
        return await self.request("GET", "/shopping", params={"horizon_days": horizon})

    async def report(self, within: float) -> dict:
        return await self.request("GET", "/report", params={"within_days": within})

    async def find_item(self, text: str) -> dict | None:
        """Позиція за назвою чи синонімом (з помилками), або за числовим id."""
        text = text.strip()
        if text.isdigit():
            card = await self.request("GET", f"/items/{text}")
            return {"id": int(text), "name": card["name"]}
        found = await self.request("GET", "/items", params={"q": text, "limit": 1})
        return found[0] if found else None

    async def ensure(self, text: str) -> dict:
        """Позиція за назвою, а якщо немає — Комора створює нову (автозаповнення ШІ).
        {id, name, created, categories}."""
        return await self.request("POST", "/items/ensure", json={"name": text.strip()})

    async def search(self, text: str, limit: int = 5) -> list[dict]:
        return await self.request("GET", "/items", params={"q": text.strip(), "limit": limit}) or []

    async def item_stock(self, item_id: int) -> list[dict]:
        return await self.request("GET", f"/items/{item_id}/stock") or []

    async def locations(self) -> list[dict]:
        return await self.request("GET", "/locations") or []

    # --- дії
    async def want(self, item_id: int, qty: float | None = None, note: str | None = None) -> None:
        await self.request("PUT", f"/shopping/{item_id}", json={"qty": qty, "note": note})

    async def skip(self, item_id: int, days: int) -> None:
        await self.request("POST", f"/shopping/{item_id}/skip", json={"days": days})

    async def bought(self, item_id: int, qty: float | None = None, unit: str | None = None) -> dict:
        body = {"qty": qty, "unit": unit} if qty is not None else {}
        return await self.request("POST", f"/shopping/{item_id}/bought", json=body)

    async def write_off(self, body: dict) -> dict:
        return await self.request("POST", "/documents/writeoff", json=body)

    async def receipt(self, body: dict) -> dict:
        return await self.request("POST", "/documents/receipt", json=body)

    async def habits(self, item_id: int) -> dict:
        return await self.request("GET", f"/items/{item_id}/habits")

    # --- живі оновлення
    async def events(self) -> AsyncIterator[str]:
        """Теми змін із /api/events (SSE). Закінчується, коли з'єднання рветься."""
        async with self._session.get(
            f"{self.url}/api/events",
            headers={**self._headers, "Accept": "text/event-stream"},
            timeout=aiohttp.ClientTimeout(total=None, sock_read=90),
        ) as r:
            if r.status == 401:
                raise KomoraAuthError("недійсний токен")
            if r.status >= 400:
                raise KomoraError(f"HTTP {r.status}")
            async for raw in r.content:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("data:"):
                    yield line[5:].strip()
