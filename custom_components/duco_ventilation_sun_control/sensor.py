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
    UnitOfTemperature,
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

COMMBOARD_SENSORS: tuple[DucoboxSensorEntityDescription, ...] = (
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
)

SENSORS: tuple[DucoboxSensorEntityDescription, ...] = (
    # Temperature sensors
    # relevant ducobox documentation: https://www.duco.eu/Wes/CDN/1/Attachments/installation-guide-DucoBox-Energy-Comfort-(Plus)-(en)_638635518879333838.pdf
    # Oda = outdoor -> box
    DucoboxSensorEntityDescription(
        key="TempOda",
        name="Outdoor Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda data: _process_temperature(
            data.get('Ventilation', {}).get('Sensor', {}).get('TempOda', {}).get('Val')
        ),
    ),
    # Sup = box -> house
    DucoboxSensorEntityDescription(
        key="TempSup",
        name="Supply Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda data: _process_temperature(
            data.get('Ventilation', {}).get('Sensor', {}).get('TempSup', {}).get('Val')
        ),
    ),
    # Eta = house -> box
    DucoboxSensorEntityDescription(
        key="TempEta",
        name="Extract Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda data: _process_temperature(
            data.get('Ventilation', {}).get('Sensor', {}).get('TempEta', {}).get('Val')
        ),
    ),
    # Eha = box -> outdoor
    DucoboxSensorEntityDescription(
        key="TempEha",
        name="Exhaust Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
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

    # Filter time remaining
    DucoboxSensorEntityDescription(
        key="TimeFilterRemain",
        name="Filter Time Remaining",
        native_unit_of_measurement=UnitOfTime.DAYS,  # Assuming the value is in days
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
            key='Mode',
            name='Ventilation Mode',
            value_fn=lambda node: node.get('Ventilation', {}).get('Mode'),
            sensor_key='Mode',
            node_type='BOX',
        ),
        DucoboxNodeSensorEntityDescription(
            key='State',
            name='Ventilation State',
            value_fn=lambda node: node.get('Ventilation', {}).get('State'),
            sensor_key='State',
            node_type='BOX',
        ),
        DucoboxNodeSensorEntityDescription(
            key='FlowLvlTgt',
            name='Flow Level Target',
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda node: node.get('Ventilation', {}).get('FlowLvlTgt'),
            sensor_key='FlowLvlTgt',
            node_type='BOX',
        ),
        DucoboxNodeSensorEntityDescription(
            key='TimeStateRemain',
            name='Time State Remaining',
            native_unit_of_measurement=UnitOfTime.SECONDS,
            value_fn=lambda node: node.get('Ventilation', {}).get('TimeStateRemain'),
            sensor_key='TimeStateRemain',
            node_type='BOX',
        ),
        DucoboxNodeSensorEntityDescription(
            key='TimeStateEnd',
            name='Time State End',
            native_unit_of_measurement=UnitOfTime.SECONDS,
            value_fn=lambda node: node.get('Ventilation', {}).get('TimeStateEnd'),
            sensor_key='TimeStateEnd',
            node_type='BOX',
        ),
    ],
    'UCCO2': [
        DucoboxNodeSensorEntityDescription(
            key='Temp',
            name='Temperature',
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            value_fn=lambda node: _process_node_temperature(
                node.get('Sensor', {}).get('data', {}).get('Temp')
            ),
            sensor_key='Temp',
            node_type='UCCO2',
        ),
        DucoboxNodeSensorEntityDescription(
            key='Co2',
            name='CO₂',
            native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
            device_class=SensorDeviceClass.CO2,
            value_fn=lambda node: _process_node_co2(
                node.get('Sensor', {}).get('data', {}).get('Co2')
            ),
            sensor_key='Co2',
            node_type='UCCO2',
        ),
        DucoboxNodeSensorEntityDescription(
            key='IaqCo2',
            name='CO₂ Air Quality',
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda node: _process_node_iaq(
                node.get('Sensor', {}).get('data', {}).get('IaqCo2')
            ),
            sensor_key='IaqCo2',
            node_type='UCCO2',
        ),
    ],
    'BSRH': [
        DucoboxNodeSensorEntityDescription(
            key='Temp',
            name='Temperature',
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            value_fn=lambda node: _process_node_temperature(
                node.get('Sensor', {}).get('data', {}).get('Temp')
            ),
            sensor_key='Temp',
            node_type='BSRH',
        ),
        DucoboxNodeSensorEntityDescription(
            key='Rh',
            name='Relative Humidity',
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.HUMIDITY,
            value_fn=lambda node: _process_node_humidity(
                node.get('Sensor', {}).get('data', {}).get('Rh')
            ),
            sensor_key='Rh',
            node_type='BSRH',
        ),
        DucoboxNodeSensorEntityDescription(
            key='IaqRh',
            name='Humidity Air Quality',
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda node: _process_node_iaq(
                node.get('Sensor', {}).get('data', {}).get('IaqRh')
            ),
            sensor_key='IaqRh',
            node_type='BSRH',
        ),
    ],
    'VLVRH': [
        DucoboxNodeSensorEntityDescription(
            key='Mode',
            name='Ventilation Mode',
            value_fn=lambda node: node.get('Ventilation', {}).get('Mode'),
            sensor_key='Mode',
            node_type='VLVRH',
        ),
        DucoboxNodeSensorEntityDescription(
            key='FlowLvlTgt',
            name='Flow Level Target',
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda node: node.get('Ventilation', {}).get('FlowLvlTgt'),
            sensor_key='FlowLvlTgt',
            node_type='VLVRH',
        ),
        DucoboxNodeSensorEntityDescription(
            key='IaqRh',
            name='Humidity Air Quality',
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda node: _process_node_iaq(
                node.get('Sensor', {}).get('data', {}).get('IaqRh')
            ),
            sensor_key='IaqRh',
            node_type='VLVRH',
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
        return value  # Assuming value is in days
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
        _LOGGER.debug(f"Data received from /info: {data}")

        nodes_response = duco_client.get_nodes()
        _LOGGER.debug(f"Data received from /nodes: {nodes_response}")

        # Convert nodes_response.Nodes (which is a list of NodeInfo objects) to list of dicts
        data['Nodes'] = [node.dict() for node in nodes_response.Nodes]
        return data

async def async_setup_entry(
    hass: HomeAssistant,
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

    comms_name = coordinator.data.get("General", {}).get("Lan", {}).get("HostName", {}).get("Val", "")
    comms_serial_number = coordinator.data.get("General", {}).get("Board", {}).get("SerialBoardComm", {}).get("Val", "")
    comms_subtype = coordinator.data.get("General", {}).get("Board", {}).get("CommSubTypeName", {}).get("Val", "")

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=comms_name,
        manufacturer="DUCO Ventilation & Sun Control",
        model=comms_subtype,
        serial_number=comms_serial_number,
        sw_version=coordinator.data.get("General", {}).get("Board", {}).get("SwVersionComm", {}).get("Val", "Unknown Version"),
    )

    entities: list[SensorEntity] = []

    # Add main Ducobox sensors
    for description in COMMBOARD_SENSORS:
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
        box_name = coordinator.data.get("General", {}).get("Board", {}).get("BoxName", {}).get("Val", "")
        node_type = node.get('General', {}).get('Type', {}).get('Val', 'Unknown')
        box_sw_version = coordinator.data.get("General", {}).get("Board", {}).get("SwVersionBox", {}).get("Val", "")
        box_serial_number = coordinator.data.get("General", {}).get("Board", {}).get("SerialBoardBox", {}).get("Val", "")

        # Create device info for the node
        node_device_id = f"{device_id}-{node_id}"

        if node.get('General', {}).get('Type', {}).get('Val') == 'BOX':
            node_device_info = DeviceInfo(
                identifiers={(DOMAIN, node_device_id)},
                name=box_name,
                manufacturer="DUCO Ventilation & Sun Control",
                model=box_name,
                sw_version=box_sw_version,
                serial_number=box_serial_number,
                via_device=(DOMAIN, device_id),
            )
        else:
            node_device_info = DeviceInfo(
                identifiers={(DOMAIN, node_device_id)},
                name=node_type,
                manufacturer="DUCO Ventilation & Sun Control",
                model=node_type,
                via_device=(DOMAIN, f"{device_id}-1"),
            )
            


        # Get the sensors for this node type
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
                    device_id=device_id,
                    node_name=node_type,
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
    ) -> None:
        """Initialize a Ducobox node sensor entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = device_info
        self._attr_unique_id = unique_id
        self._node_id = node_id
        # Updated entity name
        self._attr_name = description.name
        # self._attr_suggested_object_id = f"{device_id}_{node_name}_{description.name}".lower().replace(' ', '_')

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        # Fetch the latest data for this node
        nodes = self.coordinator.data.get('Nodes', [])
        for node in nodes:
            if node.get('Node') == self._node_id:
                return self.entity_description.value_fn(node)
        return None