from __future__ import annotations

import asyncio
import logging
from typing import Any
from datetime import timedelta
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SCAN_INTERVAL, MANUFACTURER
from .coordinator import DucoboxCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Ducobox select entities from a config entry."""
    refresh_time = entry.options.get("refresh_time", SCAN_INTERVAL.total_seconds())

    coordinator = DucoboxCoordinator(hass, update_interval=timedelta(seconds=refresh_time))
    await coordinator.async_config_entry_first_refresh()

    mac_address = get_mac_address(coordinator)
    if not mac_address:
        _LOGGER.error("No MAC address found; skipping select entities.")
        return

    device_id = mac_address.replace(":", "").lower()
    nodes = coordinator.data.get("Nodes", [])
    box_device_ids = get_box_device_ids(device_id, nodes)

    entities = await create_select_entities(hass, coordinator, device_id, nodes, box_device_ids)
    if entities:
        async_add_entities(entities, update_before_add=True)


def get_mac_address(coordinator: DucoboxCoordinator) -> str | None:
    """Retrieve MAC address from coordinator data."""
    return coordinator.data.get("General", {}).get("Lan", {}).get("Mac", {}).get("Val")


def get_box_device_ids(device_id: str, nodes: list[dict]) -> dict[int, str]:
    """Extract BOX node device IDs."""
    box_ids = {}
    for node in nodes:
        if node.get("General", {}).get("Type", {}).get("Val") == "BOX":
            node_id = int(node.get("Node"))
            box_ids[node_id] = f"{device_id}-{node_id}"
    _LOGGER.debug(f"[SELECT] BOX device IDs: {box_ids}")
    return box_ids


async def create_select_entities(
    hass: HomeAssistant,
    coordinator: DucoboxCoordinator,
    device_id: str,
    nodes: list[dict],
    box_device_ids: dict[int, str],
) -> list[SelectEntity]:
    """Create all select entities for Ducobox nodes."""
    entities = []

    for node in nodes:
        node_id = node.get("Node")
        node_type = node.get("General", {}).get("Type", {}).get("Val", "Unknown")
        ventilation = node.get("Ventilation", {})
        mode = ventilation.get("Mode")

        if mode in (None, "-"):
            _LOGGER.debug(f"[SELECT] Skipping node {node_id}: no ventilation mode")
            continue

        parent_val = node.get("General", {}).get("Parent", {}).get("Val")
        try:
            parent_box_id = int(parent_val)
        except (TypeError, ValueError):
            parent_box_id = None

        via_device_id = box_device_ids.get(parent_box_id)
        via_device = (DOMAIN, via_device_id) if via_device_id else None

        try:
            actions_response = await hass.async_add_executor_job(
                coordinator.client.get_actions_node, node_id
            )
            ventilation_action = next(
                (a for a in actions_response.Actions if a.Action == "SetVentilationState" and hasattr(a, "Enum")),
                None,
            )
            if not ventilation_action or not ventilation_action.Enum:
                continue

            if node_type == "BOX":
                model = coordinator.data.get("General", {}).get("Board", {}).get("BoxName", {}).get("Val", "Unknown").capitalize()
                model = node_type

            options = [opt.strip() for opt in ventilation_action.Enum if isinstance(opt, str)]
            node_device_id = f"{device_id}-{node_id}"
            device_info = DeviceInfo(
                identifiers={(DOMAIN, node_device_id)},
                name=node_type,
                manufacturer=MANUFACTURER,
                model=model,
                via_device=via_device,
            )
            unique_id = f"{node_device_id}-select-ventilation_mode"

            entity = DucoboxModeSelect(
                coordinator=coordinator,
                device_info=device_info,
                unique_id=unique_id,
                node_id=node_id,
                options=options,
            )
            entities.append(entity)

            _LOGGER.debug(f"[SELECT] Created select for node {node_id} with options {options}")

        except Exception as e:
            _LOGGER.warning(f"[SELECT] Failed to retrieve ventilation actions for node {node_id}: {e}")

    return entities


class DucoboxModeSelect(CoordinatorEntity[DucoboxCoordinator], SelectEntity):
    """Select entity for Ducobox ventilation mode."""

    def __init__(
        self,
        coordinator: DucoboxCoordinator,
        device_info: DeviceInfo,
        unique_id: str,
        node_id: int,
        options: list[str],
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = unique_id
        self._attr_name = f"{device_info['name']} Ventilation Mode"
        self._attr_options = options
        self._node_id = node_id

    @property
    def current_option(self) -> str | None:
        """Return the current ventilation mode."""
        nodes = self.coordinator.data.get("Nodes", [])
        for node in nodes:
            if node.get("Node") == self._node_id:
                state = node.get("Ventilation", {}).get("State")
                if isinstance(state, str) and state in self._attr_options:
                    return state
                _LOGGER.warning(f"[SELECT] Invalid current state '{state}' for node {self._node_id}")
                return None
        _LOGGER.warning(f"[SELECT] Node {self._node_id} not found")
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the ventilation mode."""
        _LOGGER.debug(f"[SELECT] Setting node {self._node_id} to {option}")
        try:
            await self.coordinator.hass.async_add_executor_job(
                self.coordinator.client.change_action_node,
                "SetVentilationState",
                option,
                self._node_id,
            )
            await asyncio.sleep(0.5)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"[SELECT] Failed to set mode '{option}' for node {self._node_id}: {e}")