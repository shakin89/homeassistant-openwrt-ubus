"""Support for OpenWrt router system information sensors."""

from __future__ import annotations

from datetime import timedelta
import logging
import re
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    PERCENTAGE,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfElectricPotential,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import CONF_WIRELESS_SOFTWARE, DEFAULT_WIRELESS_SOFTWARE, DOMAIN
from .Ubus import IwinfoUbus, Ubus

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)  # System info doesn't change frequently

SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key="uptime",
        name="Uptime",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=None,  # Main sensor, not diagnostic
        icon="mdi:clock-outline",
    ),
    SensorEntityDescription(
        key="load_1",
        name="Load Average (1m)",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        icon="mdi:speedometer",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="load_5",
        name="Load Average (5m)",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        icon="mdi:speedometer",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="load_15",
        name="Load Average (15m)",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        icon="mdi:speedometer",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="memory_total",
        name="Total Memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        icon="mdi:memory",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="memory_free",
        name="Free Memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        icon="mdi:memory",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="memory_buffered",
        name="Buffered Memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        icon="mdi:memory",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="memory_shared",
        name="Shared Memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        icon="mdi:memory",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="memory_usage_percent",
        name="Memory Usage",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:memory",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="swap_total",
        name="Total Swap",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        icon="mdi:harddisk",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="swap_free",
        name="Free Swap",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        icon="mdi:harddisk",
        entity_category=None,
    ),
    # Board/Hardware information sensors
    SensorEntityDescription(
        key="board_kernel",
        name="Kernel Version",
        icon="mdi:chip",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="board_hostname",
        name="Hostname",
        icon="mdi:router-network",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="board_model",
        name="Board Model",
        icon="mdi:developer-board",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="board_system",
        name="System",
        icon="mdi:chip",
        entity_category=None,
    ),
    # QModem Base Information sensors
    SensorEntityDescription(
        key="qmodem_manufacturer",
        name="Modem Manufacturer",
        icon="mdi:sim",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_revision",
        name="Modem Revision",
        icon="mdi:sim",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_at_port",
        name="Modem AT Port",
        icon="mdi:serial-port",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_temperature",
        name="Modem Temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_voltage",
        name="Modem Voltage",
        icon="mdi:flash",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_connect_status",
        name="Modem Connect Status",
        icon="mdi:connection",
        entity_category=None,
    ),
    # QModem SIM Information sensors
    SensorEntityDescription(
        key="qmodem_sim_status",
        name="SIM Status",
        icon="mdi:sim",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_isp",
        name="Internet Service Provider",
        icon="mdi:web",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_sim_slot",
        name="SIM Slot",
        icon="mdi:sim",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_imei",
        name="IMEI",
        icon="mdi:sim",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_imsi",
        name="IMSI",
        icon="mdi:sim",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_iccid",
        name="ICCID",
        icon="mdi:sim",
        entity_category=None,
    ),
    # QModem Signal Quality sensors (progress_bar type)
    SensorEntityDescription(
        key="qmodem_lte_rsrp",
        name="LTE RSRP",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dBm",
        icon="mdi:signal-cellular-3",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_lte_rsrq",
        name="LTE RSRQ",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dB",
        icon="mdi:signal-cellular-3",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_lte_rssi",
        name="LTE RSSI",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dBm",
        icon="mdi:signal-cellular-3",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_lte_sinr",
        name="LTE SINR",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dB",
        icon="mdi:signal-cellular-3",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_nr5g_rsrp",
        name="5G NR RSRP",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dBm",
        icon="mdi:signal-5g",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_nr5g_rsrq",
        name="5G NR RSRQ",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dB",
        icon="mdi:signal-5g",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="qmodem_nr5g_sinr",
        name="5G NR SINR",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dB",
        icon="mdi:signal-5g",
        entity_category=None,
    ),
]

# Device statistics sensor descriptions (per connected device)
DEVICE_SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key="signal",
        name="Signal Strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dBm",
        icon="mdi:signal",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="signal_avg",
        name="Average Signal Strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dBm",
        icon="mdi:signal",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="noise",
        name="Noise Level",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dBm",
        icon="mdi:signal-variant",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="connected_time",
        name="Connected Time",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:clock-outline",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="rx_rate",
        name="RX Rate",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Mbps",
        icon="mdi:download",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="tx_rate",
        name="TX Rate",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Mbps",
        icon="mdi:upload",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="rx_packets",
        name="RX Packets",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:download",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="tx_packets",
        name="TX Packets",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:upload",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="rx_bytes",
        name="RX Data",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        icon="mdi:download",
        entity_category=None,
    ),
    SensorEntityDescription(
        key="tx_bytes",
        name="TX Data",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        icon="mdi:upload",
        entity_category=None,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    
    """Set up OpenWrt system sensors from a config entry."""
    # Create system info coordinator
    system_coordinator = SystemInfoCoordinator(hass, entry)

    # Create device statistics coordinator
    device_coordinator = DeviceStatisticsCoordinator(hass, entry)

    # Create qmodem coordinator
    qmodem_coordinator = QModemCoordinator(hass, entry)

    # Store async_add_entities for dynamic entity management
    system_coordinator.async_add_entities = async_add_entities
    device_coordinator.async_add_entities = async_add_entities
    qmodem_coordinator.async_add_entities = async_add_entities

    # Fetch initial data
    await system_coordinator.async_config_entry_first_refresh()
    await device_coordinator.async_config_entry_first_refresh()
    await qmodem_coordinator.async_config_entry_first_refresh()
    
    # Create basic system sensor entities (excluding qmodem sensors)
    basic_sensors = [
        desc for desc in SENSOR_DESCRIPTIONS 
        if not desc.key.startswith("qmodem_")
    ]
    entities = [
        SystemInfoSensor(system_coordinator, description)
        for description in basic_sensors
    ]

    # Create qmodem sensors if qmodem data is available
    if qmodem_coordinator.data and qmodem_coordinator._has_qmodem_data():
        qmodem_sensors = [
            desc for desc in SENSOR_DESCRIPTIONS 
            if desc.key.startswith("qmodem_")
        ]
        entities.extend([
            QModemSensor(qmodem_coordinator, description)
            for description in qmodem_sensors
        ])
        # Mark that QModem entities have been created to prevent duplicates
        qmodem_coordinator.qmodem_entities_created = True
        _LOGGER.info("QModem detected, created %d qmodem sensor entities", len(qmodem_sensors))
    else:
        _LOGGER.info("QModem not detected, qmodem sensor entities not created")

    # Create device statistics entities for each connected device
    if device_coordinator.data:
        for mac_address in device_coordinator.data.keys():
            # Track initial devices to prevent duplicates later
            device_coordinator.known_devices.add(mac_address)
            entities.extend([
                DeviceStatisticsSensor(device_coordinator, description, mac_address)
                for description in DEVICE_SENSOR_DESCRIPTIONS
            ])
        _LOGGER.info("Created device statistics sensors for %d initial devices", 
                    len(device_coordinator.data))
    
    async_add_entities(entities, True)

    # Register cleanup callbacks
    entry.async_on_unload(system_coordinator.async_shutdown)
    entry.async_on_unload(device_coordinator.async_shutdown)
    entry.async_on_unload(qmodem_coordinator.async_shutdown)


class SystemInfoCoordinator(DataUpdateCoordinator):
    """Class to manage fetching system information from the router."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.host = entry.data[CONF_HOST]
        self.username = entry.data[CONF_USERNAME]
        self.password = entry.data[CONF_PASSWORD]

        # Get Home Assistant's HTTP client session
        session = async_get_clientsession(hass)

        self.url = f"http://{self.host}/ubus"
        self.ubus = Ubus(self.url, self.username, self.password, session=session)

        self.async_add_entities = None  # Will be set in async_setup_entry

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_system_{self.host}",
            update_interval=SCAN_INTERVAL,
        )

    async def async_shutdown(self):
        """Shutdown the coordinator and close connections."""
        try:
            await self.ubus.close()
        except Exception as exc:
            _LOGGER.debug("Error closing ubus connection: %s", exc)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update system information via ubus API."""
        try:
            # Ensure connection
            if await self.ubus.connect() is None:
                raise UpdateFailed("Failed to connect to router")

            # Get system info and board info
            system_info = await self.ubus.system_info()
            board_info = await self.ubus.system_board()

            if not system_info:
                raise UpdateFailed("Failed to get system information")

            _LOGGER.debug("System info received: %s", system_info)
            _LOGGER.debug("Board info received: %s", board_info)

            # Process the data (excluding qmodem)
            processed_data = self._process_system_info(system_info, board_info)
            _LOGGER.debug("Processed system data: %s", processed_data)

            return processed_data

        except Exception as exc:
            _LOGGER.warning("Failed to update system info: %s", exc)
            raise UpdateFailed(f"Error fetching system info: {exc}") from exc

    def _process_system_info(
        self,
        system_info: dict[str, Any],
        board_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process raw system info into sensor data."""
        data = {}

        # Uptime (usually in seconds)
        if "uptime" in system_info:
            data["uptime"] = system_info["uptime"]

        # Load averages
        if "load" in system_info and isinstance(system_info["load"], list):
            load = system_info["load"]
            if len(load) >= 3:
                data["load_1"] = load[0] / 1000
                data["load_5"] = load[1] / 1000
                data["load_15"] = load[2] / 1000

        # Memory information (convert bytes to megabytes)
        if "memory" in system_info:
            memory = system_info["memory"]
            if "total" in memory:
                data["memory_total"] = round(memory["total"] / (1024 * 1024), 1)
            if "free" in memory:
                data["memory_free"] = round(memory["free"] / (1024 * 1024), 1)
            if "buffered" in memory:
                data["memory_buffered"] = round(memory["buffered"] / (1024 * 1024), 1)
            if "shared" in memory:
                data["memory_shared"] = round(memory["shared"] / (1024 * 1024), 1)

            # Calculate memory usage percentage
            if "total" in memory and "free" in memory:
                total = memory["total"]
                free = memory["free"]
                if total > 0:
                    used = total - free
                    data["memory_usage_percent"] = round((used / total) * 100, 1)

        # Swap information (convert bytes to megabytes)
        if "swap" in system_info:
            swap = system_info["swap"]
            if "total" in swap:
                data["swap_total"] = round(swap["total"] / (1024 * 1024), 1)
            if "free" in swap:
                data["swap_free"] = round(swap["free"] / (1024 * 1024), 1)

        # Board information
        if board_info:
            if "kernel" in board_info:
                data["board_kernel"] = board_info["kernel"]
            if "hostname" in board_info:
                data["board_hostname"] = board_info["hostname"]
            if "model" in board_info:
                data["board_model"] = board_info["model"]
            if "system" in board_info:
                data["board_system"] = board_info["system"]

        return data



class QModemCoordinator(DataUpdateCoordinator):
    """Class to manage fetching QModem information from the router."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.host = entry.data[CONF_HOST]
        self.username = entry.data[CONF_USERNAME]
        self.password = entry.data[CONF_PASSWORD]

        # Get Home Assistant's HTTP client session
        session = async_get_clientsession(hass)

        self.url = f"http://{self.host}/ubus"
        self.ubus = Ubus(self.url, self.username, self.password, session=session)

        # QModem management attributes
        self.qmodem_entities_created = False
        self.async_add_entities = None  # Will be set in async_setup_entry
        self.qmodem_entities = []  # Track created qmodem entities

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_qmodem_{self.host}",
            update_interval=SCAN_INTERVAL,
        )

    async def async_shutdown(self):
        """Shutdown the coordinator and close connections."""
        try:
            await self.ubus.close()
        except Exception as exc:
            _LOGGER.debug("Error closing ubus connection: %s", exc)

    def _has_qmodem_data(self) -> bool:
        """Check if current data contains valid qmodem information."""
        if not self.data:
            return False
        
        # Check if any qmodem sensor key has data
        qmodem_keys = [desc.key for desc in SENSOR_DESCRIPTIONS if desc.key.startswith("qmodem_")]
        return any(key in self.data and self.data[key] is not None for key in qmodem_keys)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update QModem information via ubus API."""
        try:
            # Ensure connection
            if await self.ubus.connect() is None:
                raise UpdateFailed("Failed to connect to router")

            # Try to get QModem info
            qmodem_info = None
            qmodem_available = False
            try:
                qmodem_info = await self.ubus.get_qmodem_info()
                qmodem_available = qmodem_info is not None and bool(qmodem_info.get("info"))
            except Exception as exc:
                _LOGGER.debug("QModem info not available: %s", exc)
                qmodem_available = False

            _LOGGER.debug("QModem available: %s", qmodem_available)
            if qmodem_info:
                _LOGGER.debug("QModem info received: %s", qmodem_info)

            # Manage qmodem entities dynamically
            await self._manage_qmodem_entities(qmodem_available)

            # Process the qmodem data
            if qmodem_info and qmodem_available:
                processed_data = self._process_qmodem_info(qmodem_info)
                _LOGGER.debug("Processed qmodem data: %s", processed_data)
                return processed_data
            else:
                # Return empty dict if no qmodem data
                return {}

        except Exception as exc:
            _LOGGER.warning("Failed to update qmodem info: %s", exc)
            raise UpdateFailed(f"Error fetching qmodem info: {exc}") from exc

    async def _manage_qmodem_entities(self, qmodem_available: bool) -> None:
        """Manage qmodem entities - create when available, mark unavailable when not."""
        if self.async_add_entities is None:
            return

        # QModem became available - create entities
        if qmodem_available and not self.qmodem_entities_created:
            _LOGGER.info("QModem became available, creating qmodem sensor entities")
            
            # Get entity registry to check for existing entities
            entity_registry = er.async_get(self.hass)
            
            qmodem_sensors = [
                desc for desc in SENSOR_DESCRIPTIONS 
                if desc.key.startswith("qmodem_")
            ]
            
            new_entities = []
            for description in qmodem_sensors:
                key_without_prefix = description.key.replace("qmodem_", "")
                unique_id = f"{self.host}_qmodem_{key_without_prefix}"
                existing_entity_id = entity_registry.async_get_entity_id(
                    "sensor", DOMAIN, unique_id
                )
                
                if existing_entity_id:
                    _LOGGER.debug(
                        "QModem sensor entity %s already exists with entity_id %s, skipping creation",
                        unique_id, existing_entity_id
                    )
                    continue
                
                new_entities.append(QModemSensor(self, description))
            
            if new_entities:
                self.qmodem_entities.extend(new_entities)
                self.async_add_entities(new_entities, True)
                _LOGGER.info("Created %d new qmodem sensor entities", len(new_entities))
            else:
                _LOGGER.debug("No new qmodem sensor entities to create (all already exist)")
            
            self.qmodem_entities_created = True

        # QModem became unavailable - entities will show as unavailable through their available property
        elif not qmodem_available and self.qmodem_entities_created:
            _LOGGER.info("QModem became unavailable, qmodem sensor entities will show as unavailable")
            # Note: Entities will automatically show as unavailable through their available property

    def _process_qmodem_info(self, qmodem_info: dict[str, Any]) -> dict[str, Any]:
        """Process QModem information and extract relevant sensors."""
        data = {}
        
        # Navigate to the modem_info list
        info_list = qmodem_info.get("info", [])
        if not info_list:
            return data

        for info_item in info_list:
            modem_info_list = info_item.get("modem_info", [])
            if not modem_info_list:
                continue

            # Track current context (LTE or NR5G) as we process items
            current_context = "lte"  # Default context

            # Process each modem info item
            for item in modem_info_list:
                class_origin = item.get("class_origin", "")
                key = item.get("key", "")
                value = item.get("value", "")
                item_type = item.get("type", "")

                # Update context based on section markers
                if key == "LTE":
                    current_context = "lte"
                elif key == "NR5G-*":
                    current_context = "nr5g"

                # Only process Base Information, SIM Information, and progress_bar types
                if class_origin == "Base Information":
                    self._process_base_info(key, value, data)
                elif class_origin == "SIM Information":
                    self._process_sim_info(key, value, data)
                elif item_type == "progress_bar":
                    self._process_signal_info(key, value, current_context, data)

        return data

    def _process_base_info(self, key: str, value: str, data: dict[str, Any]) -> None:
        """Process base information from QModem."""
        key_mapping = {
            "manufacturer": "qmodem_manufacturer",
            "revision": "qmodem_revision",
            "at_port": "qmodem_at_port",
            "temperature": "qmodem_temperature",
            "voltage": "qmodem_voltage",
            "connect_status": "qmodem_connect_status",
        }

        data_type_mapping = {
            "voltage": int,
            "temperature": int,
            "connect_status": bool,
        }
        if key in key_mapping:
            data_type = data_type_mapping.get(key, str)
            if data_type == int:
                value = re.sub(r'[^\d.-]', '', value)  # Remove non-numeric characters
                value = int(value) if value else None
            elif data_type == bool:
                # yes true or 1
                value = value.lower() in ("yes", "true", "1")
            else:
                value = str(value)
        
            data[key_mapping[key]] = value

    def _process_sim_info(self, key: str, value: str, data: dict[str, Any]) -> None:
        """Process SIM information from QModem."""
        key_mapping = {
            "SIM Status": "qmodem_sim_status",
            "ISP": "qmodem_isp",
            "SIM Slot": "qmodem_sim_slot",
            "IMEI": "qmodem_imei",
            "IMSI": "qmodem_imsi",
            "ICCID": "qmodem_iccid",
        }

        if key in key_mapping:
            data[key_mapping[key]] = value

    def _process_signal_info(self, key: str, value: str, context: str, data: dict[str, Any]) -> None:
        """Process signal information (progress_bar type) from QModem."""
        if key == "RSRP":
            if context == "lte":
                data["qmodem_lte_rsrp"] = self._parse_numeric_value(value)
            elif context == "nr5g":
                data["qmodem_nr5g_rsrp"] = self._parse_numeric_value(value)
        elif key == "RSRQ":
            if context == "lte":
                data["qmodem_lte_rsrq"] = self._parse_numeric_value(value)
            elif context == "nr5g":
                data["qmodem_nr5g_rsrq"] = self._parse_numeric_value(value)
        elif key == "RSSI" and context == "lte":
            data["qmodem_lte_rssi"] = self._parse_numeric_value(value)
        elif key == "SINR":
            if context == "lte":
                data["qmodem_lte_sinr"] = self._parse_numeric_value(value)
            elif context == "nr5g":
                data["qmodem_nr5g_sinr"] = self._parse_numeric_value(value)

    def _parse_numeric_value(self, value: str) -> float | None:
        """Parse numeric value from string, handling various formats."""
        if not value or value in ["-", "", "N/A"]:
            return None

        try:
            # Remove any non-numeric characters except minus and decimal point
            numeric_match = re.search(r'-?\d+\.?\d*', str(value))
            if numeric_match:
                return float(numeric_match.group())
        except (ValueError, TypeError):
            pass
        return None


class DeviceStatisticsCoordinator(DataUpdateCoordinator):
    """Class to manage fetching device statistics from the router."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.host = entry.data[CONF_HOST]
        self.username = entry.data[CONF_USERNAME]
        self.password = entry.data[CONF_PASSWORD]
        self.wireless_sw = entry.data.get(CONF_WIRELESS_SOFTWARE, DEFAULT_WIRELESS_SOFTWARE)

        # Get Home Assistant's HTTP client session
        session = async_get_clientsession(hass)

        self.url = f"http://{self.host}/ubus"
        # Use IwinfoUbus for device statistics (same as device tracker)
        self.ubus = IwinfoUbus(self.url, self.username, self.password, session=session)

        self.ap_devices = []
        self.known_devices = set()
        self.async_add_entities = None  # Will be set in async_setup_entry

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_devices_{self.host}",
            update_interval=timedelta(seconds=30),  # Device stats change more frequently
        )

    async def async_shutdown(self):
        """Shutdown the coordinator and close connections."""
        try:
            await self.ubus.close()
        except Exception as exc:
            _LOGGER.debug("Error closing ubus connection: %s", exc)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update device statistics via ubus API."""
        try:
            # Ensure connection
            if await self.ubus.connect() is None:
                raise UpdateFailed("Failed to connect to router")

            # Get AP devices if not already retrieved
            if not self.ap_devices:
                try:
                    ap_devices_result = await self._get_ap_devices()
                    if ap_devices_result:
                        self.ap_devices.extend(ap_devices_result)
                        _LOGGER.debug("Found %d AP devices: %s", len(self.ap_devices), self.ap_devices)
                except Exception as exc:
                    _LOGGER.warning("Failed to get AP devices: %s", exc)
                    # Continue without AP devices

            # Get device statistics for all connected devices
            all_device_stats = {}

            for ap_device in self.ap_devices:
                try:
                    _LOGGER.debug("Getting statistics for AP device: %s", ap_device)
                    sta_stats_result = await self.ubus.get_sta_statistics(ap_device)
                    device_stats = self.ubus.parse_sta_statistics(sta_stats_result)

                    if device_stats:
                        _LOGGER.debug("Found %d devices with statistics on %s", len(device_stats), ap_device)
                        all_device_stats.update(device_stats)

                except Exception as exc:
                    _LOGGER.warning("Failed to get device statistics for %s: %s", ap_device, exc)
                    continue

            # Check for new devices and add sensors dynamically
            if self.async_add_entities is not None:
                new_devices = set(all_device_stats.keys()) - self.known_devices
                if new_devices:
                    _LOGGER.info("Found %d new devices for statistics: %s", len(new_devices), new_devices)
                    
                    # Get entity registry to check for existing entities
                    entity_registry = er.async_get(self.hass)
                    
                    new_entities = []
                    for mac_address in new_devices:
                        # Check each sensor type for this device
                        device_sensors_to_add = []
                        for description in DEVICE_SENSOR_DESCRIPTIONS:
                            unique_id = f"{self.host}_sensor_{mac_address}_{description.key}"
                            existing_entity_id = entity_registry.async_get_entity_id(
                                "sensor", DOMAIN, unique_id
                            )
                            
                            if existing_entity_id:
                                _LOGGER.debug(
                                    "Device sensor entity %s already exists with entity_id %s, skipping creation",
                                    unique_id, existing_entity_id
                                )
                                continue
                            
                            device_sensors_to_add.append(description)
                        
                        # Only add sensors that don't already exist
                        if device_sensors_to_add:
                            new_entities.extend([
                                DeviceStatisticsSensor(self, description, mac_address)
                                for description in device_sensors_to_add
                            ])
                        
                        self.known_devices.add(mac_address)
                    
                    # Add new entities only if there are any
                    if new_entities:
                        self.async_add_entities(new_entities, True)
                        _LOGGER.info("Created %d sensor entities for %d new devices", 
                                   len(new_entities), len(new_devices))
                    else:
                        _LOGGER.debug("No new sensor entities to create for %d devices (all already exist)", 
                                    len(new_devices))

            _LOGGER.debug("Device statistics data: %s", all_device_stats)
            return all_device_stats

        except Exception as exception:
            raise UpdateFailed(exception) from exception

    async def _get_ap_devices(self):
        """Get access point devices."""
        return self.ubus.parse_ap_devices(await self.ubus.get_ap_devices())


class SystemInfoSensor(CoordinatorEntity, SensorEntity):
    """Representation of a system information sensor."""

    def __init__(
        self,
        coordinator: SystemInfoCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.host}_{description.key}"
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the router."""
        # Try to get board info from coordinator data
        board_model = self.coordinator.data.get("board_model", "Router") if self.coordinator.data else "Router"
        board_hostname = self.coordinator.data.get("board_hostname") if self.coordinator.data else None
        board_system = self.coordinator.data.get("board_system") if self.coordinator.data else None

        # Use hostname for name if available, otherwise use host
        device_name = board_hostname or f"OpenWrt Router ({self.coordinator.host})"

        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.host)},
            name=device_name,
            manufacturer="OpenWrt",
            model=board_model,
            configuration_url=f"http://{self.coordinator.host}",
            sw_version=board_system,  # Use system info as software version
        )

    @property
    def native_value(self) -> Any:
        """Return the value reported by the sensor."""
        if not self.coordinator.data:
            return None

        return self.coordinator.data.get(self.entity_description.key)

    @property
    def available(self) -> bool:
        """Return True if coordinator is available."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        attributes = {
            "router_host": self.coordinator.host,
            "last_update": self.coordinator.last_update_success,
        }

        # Add raw system info for debugging if available
        if self.coordinator.data:
            attributes["raw_data"] = str(self.coordinator.data)

        return attributes


class QModemSensor(CoordinatorEntity, SensorEntity):
    """Representation of a QModem sensor."""

    def __init__(
        self,
        coordinator: QModemCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the QModem sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        # Remove the 'qmodem_' prefix from description.key to avoid duplication
        key_without_prefix = description.key.replace("qmodem_", "", 1)
        self._attr_unique_id = f"{coordinator.host}_qmodem_{key_without_prefix}"
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the QModem device."""
        # Create a separate device for QModem
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.host}_qmodem")},
            name=f"QModem ({self.coordinator.host})",
            manufacturer="Unknown",
            model="QModem Device",
            configuration_url=f"http://{self.coordinator.host}",
            via_device=(DOMAIN, self.coordinator.host),
        )

    @property
    def native_value(self) -> Any:
        """Return the value reported by the sensor."""
        if not self.coordinator.data:
            return None

        return self.coordinator.data.get(self.entity_description.key)

    @property
    def available(self) -> bool:
        """Return True if coordinator is available and sensor data is valid."""
        if not self.coordinator.last_update_success:
            return False
        
        if not self.coordinator.data:
            return False
            
        # QModem sensor is available if it has a value (not None)
        return self.coordinator.data.get(self.entity_description.key) is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        attributes = {
            "router_host": self.coordinator.host,
            "last_update": self.coordinator.last_update_success,
            "device_type": "qmodem",
        }

        # Add raw qmodem info for debugging if available
        if self.coordinator.data:
            attributes["raw_data"] = str(self.coordinator.data)

        return attributes


class DeviceStatisticsSensor(CoordinatorEntity, SensorEntity):
    """Representation of a device statistics sensor."""

    def __init__(
        self,
        coordinator: DeviceStatisticsCoordinator,
        description: SensorEntityDescription,
        mac_address: str,
    ) -> None:
        """Initialize the device statistics sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self.mac_address = mac_address
        # Use sensor-specific unique ID pattern to avoid collision with device tracker
        self._attr_unique_id = f"{coordinator.host}_sensor_{mac_address}_{description.key}"

        # Don't modify device name - use original MAC address format
        self._attr_name = None  # Let Home Assistant generate the name

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link this sensor to a device."""
        # Use the same device identifier as device tracker to link them together
        return DeviceInfo(
            identifiers={(DOMAIN, self.mac_address)},
            manufacturer="Unknown",
            model="WiFi Device",
            connections={("mac", self.mac_address)},
            via_device=(DOMAIN, self.coordinator.host),
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self.mac_address in self.coordinator.data
        )

    @property
    def native_value(self) -> str | int | float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data or self.mac_address not in self.coordinator.data:
            return None

        device_data = self.coordinator.data[self.mac_address]
        key = self.entity_description.key

        try:
            if key == "signal":
                return device_data.get("signal")
            if key == "signal_avg":
                return device_data.get("signal_avg")
            if key == "noise":
                return device_data.get("noise")
            if key == "connected_time":
                return device_data.get("connected_time")
            if key == "rx_rate":
                rx_data = device_data.get("rx", {})
                rate_kbps = rx_data.get("rate")
                # Convert kbps to Mbps
                return round(rate_kbps / 1000, 2) if rate_kbps else None
            if key == "tx_rate":
                tx_data = device_data.get("tx", {})
                rate_kbps = tx_data.get("rate")
                # Convert kbps to Mbps
                return round(rate_kbps / 1000, 2) if rate_kbps else None
            if key == "rx_packets":
                rx_data = device_data.get("rx", {})
                return rx_data.get("packets")
            if key == "tx_packets":
                tx_data = device_data.get("tx", {})
                return tx_data.get("packets")
            if key == "rx_bytes":
                rx_data = device_data.get("rx", {})
                bytes_value = rx_data.get("bytes")
                # Convert bytes to megabytes
                return round(bytes_value / (1024 * 1024), 2) if bytes_value else None
            if key == "tx_bytes":
                tx_data = device_data.get("tx", {})
                bytes_value = tx_data.get("bytes")
                # Convert bytes to megabytes
                return round(bytes_value / (1024 * 1024), 2) if bytes_value else None

        except (KeyError, TypeError, ValueError) as exc:
            _LOGGER.debug("Error getting %s for %s: %s", key, self.mac_address, exc)
            return None

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if not self.coordinator.data or self.mac_address not in self.coordinator.data:
            return {}

        device_data = self.coordinator.data[self.mac_address]

        attributes = {
            "mac_address": self.mac_address,
            "router_host": self.coordinator.host,
            "last_update": self.coordinator.last_update_success,
        }

        # Add additional device info
        if "authorized" in device_data:
            attributes["authorized"] = device_data["authorized"]
        if "authenticated" in device_data:
            attributes["authenticated"] = device_data["authenticated"]
        if "inactive" in device_data:
            attributes["inactive_time"] = device_data["inactive"]

        # Add wireless info
        rx_data = device_data.get("rx", {})
        tx_data = device_data.get("tx", {})

        if rx_data:
            attributes.update({
                "rx_ht": rx_data.get("ht"),
                "rx_vht": rx_data.get("vht"),
                "rx_he": rx_data.get("he"),
                "rx_mhz": rx_data.get("mhz"),
                "rx_mcs": rx_data.get("mcs"),
                "rx_40mhz": rx_data.get("40mhz"),
                "rx_short_gi": rx_data.get("short_gi"),
            })

        if tx_data:
            attributes.update({
                "tx_ht": tx_data.get("ht"),
                "tx_vht": tx_data.get("vht"),
                "tx_he": tx_data.get("he"),
                "tx_mhz": tx_data.get("mhz"),
                "tx_mcs": tx_data.get("mcs"),
                "tx_40mhz": tx_data.get("40mhz"),
                "tx_short_gi": tx_data.get("short_gi"),
                "tx_failed": tx_data.get("failed"),
                "tx_retries": tx_data.get("retries"),
            })

        return attributes
