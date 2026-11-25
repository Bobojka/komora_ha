"""Список «Покупки» як рідна сутність todo: додати, «куплено», прибрати."""
from __future__ import annotations

from decimal import Decimal
import re

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import KomoraError
from .const import DOMAIN
from .entity import KomoraEntity

NEED_UK = {
    "wanted": "додано вручну",
    "empty": "закінчилось",
    "low": "майже нема",
    "below_min": "менше норми",
    "runs_out": "скоро закінчиться",
}
# «молоко 2», «гречка 1,5»
QTY_TAIL = re.compile(r"^(.*\S)\s+(\d+(?:[.,]\d+)?)$")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ShoppingTodo(entry.runtime_data)])


def _num(v) -> str:
    return format(Decimal(str(v)).normalize(), "f")


class ShoppingTodo(KomoraEntity, TodoListEntity):
    _attr_icon = "mdi:cart-outline"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "shopping_list")

    def _qty(self, e: dict) -> str | None:
        q = e.get("wanted_qty") or e.get("suggest")
        return f"{_num(q)} {self.coordinator.unit_name(e.get('unit'))}" if q else None

    @property
    def todo_items(self) -> list[TodoItem]:
        items = []
        for e in self.coordinator.data.shopping:
            qty = self._qty(e)
            desc = [NEED_UK.get(e.get("need"), "")]
            if e.get("sku"):
                desc.append(e["sku"])
            if e.get("note"):
                desc.append(e["note"])
            if e.get("alternatives"):
                desc.append("або: " + ", ".join(a["name"] for a in e["alternatives"]))
            items.append(
                TodoItem(
                    uid=str(e["item_id"]),
                    summary=f"{e['name']} — {qty}" if qty else e["name"],
                    status=TodoItemStatus.NEEDS_ACTION,
                    description=" · ".join(x for x in desc if x) or None,
                )
            )
        return items

    async def _call(self, coro) -> None:
        try:
            await coro
        except KomoraError as e:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="api_error",
                translation_placeholders={"error": str(e)},
            ) from e
        await self.coordinator.async_request_refresh()

    async def async_create_todo_item(self, item: TodoItem) -> None:
        text, qty = (item.summary or "").strip(), None
        if m := QTY_TAIL.match(text):
            text, qty = m.group(1), float(m.group(2).replace(",", "."))
        try:
            found = await self.coordinator.api.find_item(text)
        except KomoraError as e:
            raise HomeAssistantError(str(e)) from e
        if not found:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="item_not_found",
                translation_placeholders={"item": text},
            )
        await self._call(self.coordinator.api.want(found["id"], qty, item.description))

    async def async_update_todo_item(self, item: TodoItem) -> None:
        if item.status == TodoItemStatus.COMPLETED:
            await self._call(self.coordinator.api.bought(int(item.uid)))

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        # прибрати зі списку = не пропонувати до кінця горизонту
        days = max(1, round(self.coordinator.horizon))
        for uid in uids:
            await self._call(self.coordinator.api.skip(int(uid), days))
