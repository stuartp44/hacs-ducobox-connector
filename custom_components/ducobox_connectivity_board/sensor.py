from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    TEMP_CELSIUS,
    UnitOfPressure,
    UnitOfTime,
    PERCENTAGE,
    CONCENTRATION_PARTS_PER_MILLION,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class DucoboxSensorEntityDescription(SensorEntityDescription):
    """Describes a Ducobox sensor entity."""

    value_fn: Callable[[dict], float | None]


@dataclass(frozen=True, kw_only=True)
class DucoboxNodeSensorEntityDescription(SensorEntityDescription):
    """Describes a Ducobox node sensor entity."""

    value_fn: Callable[[dict], float | None]
    sensor_key: str
    node_type: str


SENSORS: tuple[DucoboxSensorEntityDescription, ...] = (
    # Temperature sensors
    DucoboxSensorEntityDescription(
        key="TempOda",
        name="Outdoor Temperature",
        native_unit_of_measurement=TEMP_CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda data: _process_temperature(
            data.get('Ventilation', {}).get('Sensor', {}).get('TempOda', {}).get('Val')
        ),
    ),
    DucoboxSensorEntityDescription(
        key="TempSup",
        name="Supply Temperature",
        native_unit_of_measurement=TEMP_CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda data: _process_temperature(
            data.get('Ventilation', {}).get('Sensor', {}).get('TempSup', {}).get('Val')
        ),
    ),
    DucoboxSensorEntityDescription(
        key="TempEta",
        name="Exhaust Temperature",
        native_unit_of_measurement=TEMP_CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda data: _process_temperature(
            data.get('Ventilation', {}).get('Sensor', {}).get('TempEta', {}).get('Val')
        ),
    ),
    DucoboxSensorEntityDescription(
        key="TempEha",
        name="Extract Temperature",
        native_unit_of_measurement=TEMP_CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda data: _process_temperature(
            data.get('Ventilation', {}).get('Sensor', {}).get('TempEha', {}).get('Val')
        ),
    ),
    # Fan speed sensors
    DucoboxSensorEntityDescription(
        key="SpeedSup",
        name="Supply Fan Speed",
        native_unit_of_measurement="RPM",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.SPEED,
        value_fn=lambda data: _process_speed(
            data.get('Ventilation', {}).get('Fan', {}).get('SpeedSup', {}).get('Val')
        ),
    ),
    DucoboxSensorEntityDescription(
        key="SpeedEha",
        name="Exhaust Fan Speed",
        native_unit_of_measurement="RPM",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.SPEED,
        value_fn=lambda data: _process_speed(
            data.get('Ventilation', {}).get('Fan', {}).get('SpeedEha', {}).get('Val')
        ),
    ),
    # Pressure sensors
    DucoboxSensorEntityDescription(
        key="PressSup",
        name="Supply Pressure",
        native_unit_of_measurement=UnitOfPressure.PA,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.PRESSURE,
        value_fn=lambda data: _process_pressure(
            data.get('Ventilation', {}).get('Fan', {}).get('PressSup', {}).get('Val')
        ),
    ),
    DucoboxSensorEntityDescription(
        key="PressEha",
        name="Exhaust Pressure",
        native_unit_of_measurement=UnitOfPressure.PA,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.PRESSURE,
        value_fn=lambda data: _process_pressure(
            data.get('Ventilation', {}).get('Fan', {}).get('PressEha', {}).get('Val')
        ),
    ),
    # Wi-Fi signal strength
    DucoboxSensorEntityDescription(
        key="RssiWifi",
        name="Wi-Fi Signal Strength",
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        value_fn=lambda data: _process_rssi(
            data.get('General', {}).get('Lan', {}).get('RssiWifi', {}).get('Val')
        ),
    ),
    # Device uptime
    DucoboxSensorEntityDescription(
        key="UpTime",
        name="Device Uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda data: _process_uptime(
            data.get('General', {}).get('Board', {}).get('UpTime', {}).get('Val')
        ),
    ),
    # Filter time remaining
    DucoboxSensorEntityDescription(
        key="TimeFilterRemain",
        name="Filter Time Remaining",
        native_unit_of_measurement=UnitOfTime.MINUTES,  # Assuming the value is in minutes
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda data: _process_timefilterremain(
            data.get('HeatRecovery', {}).get('General', {}).get('TimeFilterRemain', {}).get('Val')
        ),
    ),
    # Bypass position
    DucoboxSensorEntityDescription(
        key="BypassPos",
        name="Bypass Position",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _process_bypass_position(
            data.get('HeatRecovery', {}).get('Bypass', {}).get('Pos', {}).get('Val')
        ),
    ),
    # Add additional sensors here if needed
)

# Define sensors for nodes based on their type
NODE_SENSORS: dict[str, list[DucoboxNodeSensorEntityDescription]] = {
    'BOX': [
        DucoboxNodeSensorEntityDescription(
            key='Temp',
            name='Temperature',
            native_unit_of_measurement=TEMP_CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            value_fn=lambda data: _process_node_temperature(data.get('Temp')),
            sensor_key='Temp',
            node_type='BOX',
        ),
        DucoboxNodeSensorEntityDescription(
            key='Rh',
            name='Relative Humidity',
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.HUMIDITY,
            value_fn=lambda data: _process_node_humidity(data.get('Rh')),
            sensor_key='Rh',
            node_type='BOX',
        ),
        DucoboxNodeSensorEntityDescription(
            key='IaqRh',
            name='Humidity Air Quality',
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda data: _process_node_iaq(data.get('IaqRh')),
            sensor_key='IaqRh',
            node_type='BOX',
        ),
    ],
    'UCCO2': [
        DucoboxNodeSensorEntityDescription(
            key='Temp',
            name='Temperature',
            native_unit_of_measurement=TEMP_CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            value_fn=lambda data: _process_node_temperature(data.get('Temp')),
            sensor_key='Temp',
            node_type='UCCO2',
        ),
        DucoboxNodeSensorEntityDescription(
            key='Co2',
            name='CO₂',
            native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
            device_class=SensorDeviceClass.CO2,
            value_fn=lambda data: _process_node_co2(data.get('Co2')),
            sensor_key='Co2',
            node_type='UCCO2',
        ),
        DucoboxNodeSensorEntityDescription(
            key='IaqCo2',
            name='CO₂ Air Quality',
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda data: _process_node_iaq(data.get('IaqCo2')),
            sensor_key='IaqCo2',
            node_type='UCCO2',
        ),
    ],
    'BSRH': [
        DucoboxNodeSensorEntityDescription(
            key='Temp',
            name='Temperature',
            native_unit_of_measurement=TEMP_CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            value_fn=lambda data: _process_node_temperature(data.get('Temp')),
            sensor_key='Temp',
            node_type='BSRH',
        ),
        DucoboxNodeSensorEntityDescription(
            key='Rh',
            name='Relative Humidity',
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.HUMIDITY,
            value_fn=lambda data: _process_node_humidity(data.get('Rh')),
            sensor_key='Rh',
            node_type='BSRH',
        ),
        DucoboxNodeSensorEntityDescription(
            key='IaqRh',
            name='Humidity Air Quality',
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda data: _process_node_iaq(data.get('IaqRh')),
            sensor_key='IaqRh',
            node_type='BSRH',
        ),
    ],
    # Add other node types and their sensors if needed
}

# Node-specific processing functions
def _process_node_temperature(value):
    """Process node temperature values."""
    if value is not None:
        return value  # Assuming value is in Celsius
    return None

def _process_node_humidity(value):
    """Process node humidity values."""
    if value is not None:
        return value  # Assuming value is in percentage
    return None

def _process_node_co2(value):
    """Process node CO₂ values."""
    if value is not None:
        return value  # Assuming value is in ppm
    return None

def _process_node_iaq(value):
    """Process node IAQ values."""
    if value is not None:
        return value  # Assuming value is in percentage
    return None

# Main sensor processing functions
def _process_temperature(value):
    """Process temperature values by dividing by 10."""
    if value is not None:
        return value / 10.0  # Convert from tenths of degrees Celsius
    return None

def _process_speed(value):
    """Process speed values."""
    if value is not None:
        return value  # Assuming value is already in RPM
    return None

def _process_pressure(value):
    """Process pressure values."""
    if value is not None:
        return value  # Assuming value is in Pa
    return None

def _process_rssi(value):
    """Process Wi-Fi signal strength."""
    if value is not None:
        return value  # Assuming value is in dBm
    return None

def _process_uptime(value):
    """Process device uptime."""
    if value is not None:
        return value  # Assuming value is in seconds
    return None

def _process_timefilterremain(value):
    """Process filter time remaining."""
    if value is not None:
        return value  # Assuming value is in minutes
    return None

def _process_bypass_position(value):
    """Process bypass position."""
    if value is not None:
        # Assuming value ranges from 0 to 255, where 255 is 100%
        return round((value / 255) * 100)
    return None

class DucoboxCoordinator(DataUpdateCoordinator):
    """Coordinator to manage data updates for Ducobox sensors."""

    def __init__(self, hass: HomeAssistant):
        super().__init__(
            hass,
            _LOGGER,
            name="Ducobox Connectivity Board",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict:
        """Fetch data from the Ducobox API."""
        try:
            return await self.hass.async_add_executor_job(self._fetch_data)
        except Exception as e:
            _LOGGER.error("Failed to fetch data from Ducobox API: %s", e)
            return {}

    def _fetch_data(self) -> dict:
        duco_client = self.hass.data[DOMAIN]
        data = duco_client.get_info()
        nodes_response = duco_client.get_nodes()
        # Convert nodes_response.Nodes (which is a list of NodeInfo objects) to list of dicts
        data['Nodes'] = [node.dict() for node in nodes_response.Nodes]
        return data

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Ducobox sensors from a config entry."""
    coordinator = DucoboxCoordinator(hass)
    await coordinator.async_config_entry_first_refresh()

    # Retrieve MAC address and format device ID and name
    mac_address = (
        coordinator.data.get("General", {})
        .get("Lan", {})
        .get("Mac", {})
        .get("Val", "unknown_mac")
    )
    device_id = mac_address.replace(":", "").lower() if mac_address else "unknown_mac"
    device_name = f"ducobox_{device_id}"

    box_name = coordinator.data.get("General", {}).get("Board", {}).get("BoxName", {}).get("Val", "Unknown Model")
    box_subtype = coordinator.data.get("General", {}).get("Board", {}).get("BoxSubTypeName", {}).get("Val", "")
    box_model = f"{box_name} {box_subtype}".replace('_', ' ').strip()

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_name,
        manufacturer="Ducobox",
        model=box_model,
        sw_version=coordinator.data.get("General", {}).get("Board", {}).get("SwVersionBox", {}).get("Val", "Unknown Version"),
    )

    entities: list[SensorEntity] = []

    # Add main Ducobox sensors
    for description in SENSORS:
        unique_id = f"{device_id}-{description.key}"
        entities.append(
            DucoboxSensorEntity(
                coordinator=coordinator,
                description=description,
                device_info=device_info,
                unique_id=unique_id,
            )
        )

    # Add node sensors
    nodes = coordinator.data.get('Nodes', [])
    for node in nodes:
        node_id = node.get('Node')
        node_type = node.get('General', {}).get('Type', {}).get('Val', 'Unknown')
        node_addr = node.get('General', {}).get('Addr', 'Unknown')
        node_name = f"Ducobox Node {node_id} ({node_type})"

        # Create device info for the node
        node_device_id = f"{device_id}_node_{node_id}"
        node_device_info = DeviceInfo(
            identifiers={(DOMAIN, node_device_id)},
            name=node_name,
            manufacturer="Ducobox",
            model=node_type,
            via_device=(DOMAIN, device_id),
        )

        # Get sensor data safely
        sensor = node.get('Sensor')
        sensor_data = sensor.get('data', {}) if isinstance(sensor, dict) else {}

        # For nodes with sensor data
        if sensor_data:
            node_sensors = NODE_SENSORS.get(node_type, [])
            for description in node_sensors:
                unique_id = f"{node_device_id}-{description.key}"
                entities.append(
                    DucoboxNodeSensorEntity(
                        coordinator=coordinator,
                        node_id=node_id,
                        description=description,
                        device_info=node_device_info,
                        unique_id=unique_id,
                        main_device_name=device_name,  # Pass main device name
                        node_name=node_name,
                    )
                )

    async_add_entities(entities)

class DucoboxSensorEntity(CoordinatorEntity[DucoboxCoordinator], SensorEntity):
    """Representation of a Ducobox sensor entity."""
    entity_description: DucoboxSensorEntityDescription

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
    entity_description: DucoboxNodeSensorEntityDescription

    def __init__(
        self,
        coordinator: DucoboxCoordinator,
        node_id: int,
        description: DucoboxNodeSensorEntityDescription,
        device_info: DeviceInfo,
        unique_id: str,
        main_device_name: str,
        node_name: str,
    ) -> None:
        """Initialize a Ducobox node sensor entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = device_info
        self._attr_unique_id = unique_id
        self._node_id = node_id
        # Include the main device name in the entity name
        self._attr_name = f"{main_device_name} {node_name} {description.name}"

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        # Fetch the latest data for this node
        nodes = self.coordinator.data.get('Nodes', [])
        for node in nodes:
            if node.get('Node') == self._node_id:
                sensor = node.get('Sensor')
                sensor_data = sensor.get('data', {}) if isinstance(sensor, dict) else {}
                return self.entity_description.value_fn(sensor_data)
        return None
