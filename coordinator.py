"""Дані Комори для HA: список покупок і звіт; оновлення — за подіями SSE."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KomoraApi, KomoraAuthError, KomoraError
from .const import (
    CONF_HORIZON,
    CONF_WITHIN,
    DEFAULT_HORIZON,
    DEFAULT_WITHIN,
    DOMAIN,
    REFRESH_TOPICS,
)

_LOGGER = logging.getLogger(__name__)

# запасне опитування, якщо потік подій мовчить
POLL = timedelta(minutes=15)


@dataclass
class KomoraData:
    shopping: list[dict] = field(default_factory=list)
    running_out: list[dict] = field(default_factory=list)
    spoiling: list[dict] = field(default_factory=list)


class KomoraCoordinator(DataUpdateCoordinator[KomoraData]):
    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: KomoraApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=POLL,
            # кілька змін поспіль (документ на кілька рядків) — одне оновлення
            request_refresh_debouncer=Debouncer(hass, _LOGGER, cooldown=1.0, immediate=True),
        )
        self.api = api
        self.units: dict[str, str] = {}
        self.version: str | None = None

    @property
    def horizon(self) -> float:
        return self.config_entry.options.get(CONF_HORIZON, DEFAULT_HORIZON)

    async def _async_setup(self) -> None:
        try:
            self.version = (await self.api.health()).get("version")
            self.units = {u["code"]: u["name"] for u in await self.api.units()}
        except KomoraAuthError as e:
            raise ConfigEntryAuthFailed(str(e)) from e
        except KomoraError as e:
            raise UpdateFailed(str(e)) from e

    async def _async_update_data(self) -> KomoraData:
        within = self.config_entry.options.get(CONF_WITHIN, DEFAULT_WITHIN)
        try:
            shopping, report = await asyncio.gather(
                self.api.shopping(self.horizon), self.api.report(within)
            )
        except KomoraAuthError as e:
            raise ConfigEntryAuthFailed(str(e)) from e
        except KomoraError as e:
            raise UpdateFailed(str(e)) from e
        return KomoraData(
            shopping=shopping.get("items", []),
            running_out=report.get("running_out", []),
            spoiling=report.get("spoiling", []),
        )

    def unit_name(self, code: str | None) -> str:
        return self.units.get(code or "", code or "")

    async def listen(self) -> None:
        """Слухає /api/events і оновлюється на зміни; при обриві — перепідключення."""
        delay = 5
        while True:
            try:
                async for topics in self.api.events():
                    delay = 5
                    if REFRESH_TOPICS & set(topics.split(",")):
                        await self.async_request_refresh()
            except KomoraAuthError:
                _LOGGER.warning("Комора: токен відкликано, живі оновлення зупинено")
                return
            except (KomoraError, asyncio.TimeoutError, OSError) as e:
                _LOGGER.debug("Комора: потік подій обірвався: %s", e)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 300)
            # поки не було потоку, могли бути зміни
            await self.async_request_refresh()
