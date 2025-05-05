from __future__ import annotations
import logging
from typing import Any
from datetime import timedelta
from retrying import retry
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN, SCAN_INTERVAL, MANUFACTURER
import asyncio
from .comm_boards import COMMBOARD_SENSORS
from .network import DUCONETWORK_SENSORS
from .nodes import NODE_SENSORS
from .boxes import BOX_SENSORS
from .calibration import CALIBRATION_SENSORS
from .ducobox_classes import DucoboxSensorEntityDescription, DucoboxNodeSensorEntityDescription
from .coordinator import DucoboxCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Ducobox sensors from a config entry."""
    refresh_time = entry.options.get("refresh_time", SCAN_INTERVAL.total_seconds())
    
    coordinator = DucoboxCoordinator(hass, update_interval=timedelta(seconds=refresh_time))
    await coordinator.async_config_entry_first_refresh()

    mac_address = get_mac_address(coordinator)
    if not mac_address:
        _LOGGER.error("No MAC address found in data, unable to create sensors")
        _LOGGER.debug(f"Data received: {coordinator.data}")
        return

    device_id = mac_address.replace(":", "").lower()
    device_info = create_device_info(coordinator, device_id)

    entities = []
    entities.extend(create_main_sensors(coordinator, device_info, device_id))
    entities.extend(create_node_sensors(coordinator, device_id))

    if entities:
        async_add_entities(entities, update_before_add=True)


def find_box_addr(nodes: list[dict]) -> int | None:
    """Find the Addr of the first node where the type is BOX."""
    for node in nodes:
        if node.get("General", {}).get("Type", {}).get("Val") == "BOX":
            return node.get("General", {}).get("Addr")
    return None


def get_mac_address(coordinator: DucoboxCoordinator) -> str | None:
    """Retrieve the MAC address from the coordinator data."""
    return (
        coordinator.data.get("General", {})
        .get("Lan", {})
        .get("Mac", {})
        .get("Val")
    )


def create_device_info(coordinator: DucoboxCoordinator, device_id: str) -> DeviceInfo:
    """Create device info for the main Ducobox."""
    data = coordinator.data
    return DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=data.get("General", {}).get("Lan", {}).get("HostName", {}).get("Val", "Unknown"),
        manufacturer=MANUFACTURER,
        model=data.get("General", {}).get("Board", {}).get("CommSubTypeName", {}).get("Val", "Unknown"),
        serial_number=data.get("General", {}).get("Board", {}).get("SerialBoardComm", {}).get("Val", "Unknown"),
        sw_version=data.get("General", {}).get("Board", {}).get("SwVersionComm", {}).get("Val", "Unknown"),
    )


def create_main_sensors(coordinator: DucoboxCoordinator, device_info: DeviceInfo, device_id: str) -> list[SensorEntity]:
    """Create main Ducobox sensors."""
    return [
        DucoboxSensorEntity(
            coordinator=coordinator,
            description=description,
            device_info=device_info,
            unique_id=f"{device_id}-{description.key}",
        )
        for description in COMMBOARD_SENSORS
    ]


def create_node_sensors(coordinator: DucoboxCoordinator, device_id: str) -> list[SensorEntity]:
    """Create sensors for each node, connecting them via the box."""
    entities = []
    nodes = coordinator.data.get("Nodes", [])
    box_device_ids = {}

    # First, create box sensors and store their device IDs
    for node in nodes:
        node_type = node.get("General", {}).get("Type", {}).get("Val", "Unknown")
        if node_type == "BOX":
            node_id = node.get("Node")
            node_device_id = f"{device_id}-{node_id}"
            box_device_ids[node_id] = node_device_id
            entities.extend(create_box_sensors(coordinator, node, node_device_id, device_id))

    # Then, create sensors for other nodes, linking them via their box
    for node in nodes:
        node_id = node.get("Node")
        node_type = node.get("General", {}).get("Type", {}).get("Val", "Unknown")
        parent_box_id = find_box_addr(nodes)

        if node_type != "BOX" and node_type != "UC":
            # Use the parent box's device ID as the via_device
            via_device_id = box_device_ids.get(parent_box_id, device_id)
            node_device_id = f"{device_id}-{node_id}"
            entities.extend(create_generic_node_sensors(coordinator, node, node_device_id, node_type, via_device_id))

    return entities

def create_box_sensors(coordinator: DucoboxCoordinator, node: dict, node_device_id: str, device_id: str) -> list[SensorEntity]:
    """Create sensors for a BOX node, including calibration and network sensors."""
    entities = []
    box_name = coordinator.data.get("General", {}).get("Board", {}).get("BoxName", {}).get("Val", "")
    box_sw_version = coordinator.data.get("General", {}).get("Board", {}).get("SwVersionBox", {}).get("Val", "")
    box_serial_number = coordinator.data.get("General", {}).get("Board", {}).get("SerialBoardBox", {}).get("Val", "")
    box_device_info = DeviceInfo(
        identifiers={(DOMAIN, node_device_id)},
        name=box_name,
        manufacturer=MANUFACTURER,
        model=box_name,
        sw_version=box_sw_version,
        serial_number=box_serial_number,
        via_device=(DOMAIN, device_id),
    )

    # Add box-specific sensors
    if box_name in BOX_SENSORS:
        for description in BOX_SENSORS[box_name]:
            entities.append(
                DucoboxNodeSensorEntity(
                    coordinator=coordinator,
                    node_id=node.get("Node"),
                    description=description,
                    device_info=box_device_info,
                    unique_id=f"{node_device_id}-{description.key}",
                    device_id=device_id,
                    node_name=box_name,
                )
            )

    # Add Duco network sensors as diagnostic sensors
    for description in DUCONETWORK_SENSORS:
        entities.append(
            DucoboxNodeSensorEntity(
                coordinator=coordinator,
                node_id=node.get("Node"),
                description=description,
                device_info=box_device_info,
                unique_id=f"{node_device_id}-{description.key}",
                device_id=device_id,
                node_name=box_name,
            )
        )

    # Add calibration sensors as diagnostic sensors
    for description in CALIBRATION_SENSORS:
        entities.append(
            DucoboxNodeSensorEntity(
                coordinator=coordinator,
                node_id=node.get("Node"),
                description=description,
                device_info=box_device_info,
                unique_id=f"{node_device_id}-{description.key}",
                device_id=device_id,
                node_name=box_name,
            )
        )

    return entities


def create_generic_node_sensors(
    coordinator: DucoboxCoordinator, node: dict, node_device_id: str, node_type: str, via_device_id: str
) -> list[SensorEntity]:
    """Create sensors for a generic node, linking them via the specified device."""
    node_device_info = DeviceInfo(
        identifiers={(DOMAIN, node_device_id)},
        name=node_type,
        manufacturer=MANUFACTURER,
        model=node_type,
        via_device=(DOMAIN, via_device_id),
    )

    return [
        DucoboxNodeSensorEntity(
            coordinator=coordinator,
            node_id=node.get("Node"),
            description=description,
            device_info=node_device_info,
            unique_id=f"{node_device_id}-{description.key}",
            device_id=via_device_id,
            node_name=node_type,
        )
        for description in NODE_SENSORS.get(node_type, [])
    ]


def create_duco_network_sensors(coordinator: DucoboxCoordinator, device_info: DeviceInfo, device_id: str) -> list[SensorEntity]:
    """Create Duco network sensors."""
    return [
        DucoboxSensorEntity(
            coordinator=coordinator,
            description=description,
            device_info=device_info,
            unique_id=f"{device_id}-{description.key}",
        )
        for description in DUCONETWORK_SENSORS
    ]


def create_calibration_sensors(coordinator: DucoboxCoordinator, device_info: DeviceInfo, device_id: str) -> list[SensorEntity]:
    """Create calibration sensors."""
    return [
        DucoboxSensorEntity(
            coordinator=coordinator,
            description=description,
            device_info=device_info,
            unique_id=f"{device_id}-{description.key}",
        )
        for description in CALIBRATION_SENSORS
    ]


class DucoboxSensorEntity(CoordinatorEntity[DucoboxCoordinator], SensorEntity):
    """Representation of a Ducobox sensor entity."""

    def __init__(
        self,
        coordinator: DucoboxCoordinator,
        description: DucoboxSensorEntityDescription,
        device_info: DeviceInfo,
        unique_id: str,
    ) -> None:
        """Initialize a Ducobox sensor entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = device_info
        self._attr_unique_id = unique_id
        self._attr_name = f"{device_info['name']} {description.name}"

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)


class DucoboxNodeSensorEntity(CoordinatorEntity[DucoboxCoordinator], SensorEntity):
    """Representation of a Ducobox node sensor entity."""

    def __init__(
        self,
        coordinator: DucoboxCoordinator,
        node_id: int,
        description: DucoboxNodeSensorEntityDescription,
        device_info: DeviceInfo,
        unique_id: str,
        device_id: str,
        node_name: str,
    ) -> None:
        """Initialize a Ducobox node sensor entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = device_info
        self._attr_unique_id = unique_id
        self._node_id = node_id
        self._attr_name = description.name

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        nodes = self.coordinator.data.get("Nodes", [])
        for node in nodes:
            if node.get("Node") == self._node_id:
                return self.entity_description.value_fn({'node_data': node, 'general_data': self.coordinator.data})
        return None