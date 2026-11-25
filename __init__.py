"""Комора — домашній облік запасів у Home Assistant.

Список покупок (todo), сенсори, дії «списати / надійшло / до покупок»
і панель Комори в бічному меню.
"""
from __future__ import annotations

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import KomoraApi
from .const import CONF_PANEL, CONF_TOKEN, CONF_URL, DOMAIN, PANEL_PATH
from .coordinator import KomoraCoordinator
from .services import async_setup_services

PLATFORMS = [Platform.SENSOR, Platform.TODO]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type KomoraConfigEntry = ConfigEntry[KomoraCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: KomoraConfigEntry) -> bool:
    api = KomoraApi(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN])
    coordinator = KomoraCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_create_background_task(hass, coordinator.listen(), f"{DOMAIN}_events")

    if entry.options.get(CONF_PANEL, True):
        # Комора сама дозволяє вбудовування (KOMORA_FRAME_ANCESTORS), вхід — її власний
        frontend.async_register_built_in_panel(
            hass,
            component_name="iframe",
            sidebar_title="Комора",
            sidebar_icon="mdi:fridge-outline",
            frontend_url_path=PANEL_PATH,
            config={"url": api.url},
            require_admin=False,
            update=True,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: KomoraConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: KomoraConfigEntry) -> bool:
    frontend.async_remove_panel(hass, PANEL_PATH, warn_if_unknown=False)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
