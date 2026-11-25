"""Сенсори: скільки в списку покупок, що закінчується, що треба доїсти."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KomoraData
from .entity import KomoraEntity

# «треба доїсти»: зіпсоване, прострочене, скоро вжити, мало днів
EAT_FIRST = {"spoiled", "check", "use_soon", "within"}


@dataclass(frozen=True, kw_only=True)
class KomoraSensorDescription(SensorEntityDescription):
    rows: Callable[[KomoraData], list[dict]]


SENSORS = (
    KomoraSensorDescription(
        key="shopping",
        icon="mdi:cart-outline",
        rows=lambda d: d.shopping,
    ),
    KomoraSensorDescription(
        key="running_out",
        icon="mdi:package-variant-remove",
        rows=lambda d: d.running_out,
    ),
    KomoraSensorDescription(
        key="eat_first",
        icon="mdi:food-apple-outline",
        rows=lambda d: [x for x in d.spoiling if x.get("reason") in EAT_FIRST],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(KomoraSensor(coordinator, d) for d in SENSORS)


class KomoraSensor(KomoraEntity, SensorEntity):
    entity_description: KomoraSensorDescription
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "поз."

    def __init__(self, coordinator, description: KomoraSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    def _rows(self) -> list[dict]:
        return self.entity_description.rows(self.coordinator.data)

    @property
    def native_value(self) -> int:
        # одна позиція може лежати кількома партіями
        return len({r["item_id"] for r in self._rows()})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        seen: dict[int, dict] = {}
        for r in self._rows():
            if r["item_id"] not in seen:
                row = {"id": r["item_id"], "name": r["name"]}
                for k in ("need", "reason", "days_left", "expires_on"):
                    if r.get(k) is not None:
                        row[k] = r[k]
                seen[r["item_id"]] = row
        rows = list(seen.values())
        return {"items": rows, "names": ", ".join(r["name"] for r in rows)}
