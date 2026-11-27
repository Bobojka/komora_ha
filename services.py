"""Дії: списати, надійшло, додати до покупок, знайти (скільки є). Позиція — назвою (можна з помилкою) або id."""
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
    ATTR_LIMIT,
    ATTR_NOTE,
    ATTR_QTY,
    ATTR_QUERY,
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
FIND = vol.Schema({
    vol.Optional(ATTR_ENTRY): cv.string,
    vol.Required(ATTR_QUERY): cv.string,
    vol.Optional(ATTR_LIMIT, default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
})
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
    async_setup_find(hass)


PRESENCE = {"yes": "є", "low": "мало", "no": "немає"}


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _paths(locations: list[dict]) -> dict[int, str]:
    by_id = {loc["id"]: loc for loc in locations}

    def path(i: int) -> str:
        parts, seen = [], set()
        while i in by_id and i not in seen:
            seen.add(i)
            parts.append(by_id[i]["name"])
            i = by_id[i].get("parent_id")
        return " / ".join(reversed(parts))

    return {i: path(i) for i in by_id}


def summarize(item: dict, lines: list[dict], paths: dict[int, str]) -> dict:
    """Залишок позиції: сума точних/приблизних, рівень чи наявність, і де лежить."""
    total = 0.0
    counted = False
    levels: list[int] = []
    presence: list[str] = []
    places: list[str] = []
    for line in lines:
        q = line.get("quantity") or {}
        form = q.get("form")
        if form in ("exact", "approx") and _num(q.get("qty")) is not None:
            total += _num(q["qty"])
            counted = True
        elif form == "level" and q.get("level") is not None:
            levels.append(int(q["level"]))
        elif form == "presence" and q.get("presence"):
            presence.append(str(q["presence"]))
        place = paths.get(line.get("location_id"))
        if place and place not in places:
            places.append(place)
    if counted:
        text = f"{round(total, 3):g} {item.get('base_unit') or ''}".strip()
    elif levels:
        text = f"рівень {max(levels)}"
    elif presence:
        best = next((p for p in ("yes", "low", "no") if p in presence), presence[0])
        text = PRESENCE.get(best, best)
    else:
        text = "немає"
    return {
        "item_id": item["id"],
        "name": item["name"],
        "unit": item.get("base_unit"),
        "qty": round(total, 3) if counted else None,
        "amount": text,
        "locations": places,
    }


def async_setup_find(hass: HomeAssistant) -> None:
    async def find(call: ServiceCall) -> ServiceResponse:
        c = _coordinator(hass, call)
        try:
            found = await c.api.search(call.data[ATTR_QUERY], call.data[ATTR_LIMIT])
            found = [i for i in found if not i.get("archived")]
            paths = _paths(await c.api.locations()) if found else {}
            items = [summarize(i, await c.api.item_stock(i["id"]), paths) for i in found]
        except KomoraError as e:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="api_error",
                translation_placeholders={"error": str(e)},
            ) from e
        return {"items": items}

    hass.services.async_register(
        DOMAIN, "find", find, schema=FIND, supports_response=SupportsResponse.ONLY,
    )
