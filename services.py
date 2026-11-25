"""Дії: списати, надійшло, додати до покупок. Позиція — назвою (можна з помилкою) або id."""
from __future__ import annotations

from functools import partial

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import KomoraError
from .const import (
    ATTR_ENTRY,
    ATTR_ITEM,
    ATTR_NOTE,
    ATTR_QTY,
    ATTR_REASON,
    ATTR_UNIT,
    DOMAIN,
    REASONS,
)
from .coordinator import KomoraCoordinator

BASE = {
    vol.Optional(ATTR_ENTRY): cv.string,
    vol.Required(ATTR_ITEM): cv.string,
    vol.Optional(ATTR_QTY): vol.Coerce(float),
    vol.Optional(ATTR_UNIT): cv.string,
    vol.Optional(ATTR_NOTE): cv.string,
}
WRITE_OFF = vol.Schema({**BASE, vol.Optional(ATTR_REASON): vol.In(REASONS)})
RECEIVE = vol.Schema(BASE)
ADD = vol.Schema(BASE)


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> KomoraCoordinator:
    entries = [
        e for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
        and (ATTR_ENTRY not in call.data or e.entry_id == call.data[ATTR_ENTRY])
    ]
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    return entries[0].runtime_data


async def _item(c: KomoraCoordinator, text: str) -> dict:
    try:
        found = await c.api.find_item(text)
    except KomoraError as e:
        raise HomeAssistantError(str(e)) from e
    if not found:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="item_not_found",
            translation_placeholders={"item": text},
        )
    return found


def async_setup_services(hass: HomeAssistant) -> None:
    async def run(action, call: ServiceCall) -> ServiceResponse:
        c = _coordinator(hass, call)
        item = await _item(c, call.data[ATTR_ITEM])
        try:
            res = await action(c, item, call.data)
        except KomoraError as e:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="api_error",
                translation_placeholders={"error": str(e)},
            ) from e
        await c.async_request_refresh()
        return {"item_id": item["id"], "name": item["name"], **(res or {})}

    async def write_off(c: KomoraCoordinator, item: dict, d: dict):
        if ATTR_QTY not in d:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="qty_required")
        return await c.api.write_off({
            "item_id": item["id"], "qty": d[ATTR_QTY], "unit": d.get(ATTR_UNIT),
            "reason": d.get(ATTR_REASON), "note": d.get(ATTR_NOTE),
        })

    async def receive(c: KomoraCoordinator, item: dict, d: dict):
        # звичне місце й кількість — як «куплено» у списку
        return await c.api.bought(item["id"], d.get(ATTR_QTY), d.get(ATTR_UNIT))

    async def add(c: KomoraCoordinator, item: dict, d: dict):
        await c.api.want(item["id"], d.get(ATTR_QTY), d.get(ATTR_NOTE))

    for name, schema, action in (
        ("write_off", WRITE_OFF, write_off),
        ("receive", RECEIVE, receive),
        ("add_to_shopping", ADD, add),
    ):
        hass.services.async_register(
            DOMAIN, name,
            partial(run, action),
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )
