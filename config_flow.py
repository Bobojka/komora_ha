"""Налаштування з інтерфейсу: адреса Комори + токен; параметри — панель і горизонти."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import KomoraApi, KomoraAuthError, KomoraError
from .const import (
    CONF_HORIZON,
    CONF_PANEL,
    CONF_TOKEN,
    CONF_URL,
    CONF_WITHIN,
    DEFAULT_HORIZON,
    DEFAULT_WITHIN,
    DOMAIN,
)

TOKEN = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def _check(hass, url: str, token: str) -> dict[str, str]:
    api = KomoraApi(async_get_clientsession(hass), url, token)
    try:
        await api.features()  # потребує токена — перевіряє і адресу, і доступ
    except KomoraAuthError:
        return {"base": "invalid_auth"}
    except KomoraError:
        return {"base": "cannot_connect"}
    return {}


class KomoraConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip().rstrip("/")
            if not url.startswith(("http://", "https://")):
                errors[CONF_URL] = "bad_url"
            else:
                await self.async_set_unique_id(url.lower())
                self._abort_if_unique_id_configured()
                errors = await _check(self.hass, url, user_input[CONF_TOKEN].strip())
                if not errors:
                    return self.async_create_entry(
                        title="Комора",
                        data={CONF_URL: url, CONF_TOKEN: user_input[CONF_TOKEN].strip()},
                    )
        schema = vol.Schema(
            {
                vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
                vol.Required(CONF_TOKEN): TOKEN,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            errors = await _check(self.hass, entry.data[CONF_URL], token)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: token})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): TOKEN}),
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return KomoraOptionsFlow()


class KomoraOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_PANEL: bool(user_input[CONF_PANEL]),
                    CONF_HORIZON: int(user_input[CONF_HORIZON]),
                    CONF_WITHIN: int(user_input[CONF_WITHIN]),
                }
            )
        o = self.config_entry.options

        def days(lo: int, hi: int) -> NumberSelector:
            return NumberSelector(
                NumberSelectorConfig(min=lo, max=hi, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="дн.")
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_PANEL, default=o.get(CONF_PANEL, True)): BooleanSelector(),
                vol.Required(CONF_HORIZON, default=o.get(CONF_HORIZON, DEFAULT_HORIZON)): days(1, 60),
                vol.Required(CONF_WITHIN, default=o.get(CONF_WITHIN, DEFAULT_WITHIN)): days(0, 30),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
