"""Support for OpenWrt router QModem information sensors."""

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
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from ..const import DOMAIN
from ..Ubus import Ubus

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=2)  # QModem info changes more frequently

SENSOR_DESCRIPTIONS = [
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
    # QModem Signal Quality sensors
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenWrt QModem sensors from a config entry."""
    # Check if modem_ctrl is available from the initial setup
    modem_ctrl_available = hass.data.get(DOMAIN, {}).get("modem_ctrl_available", False)
    
    # Create QModem coordinator
    coordinator = QModemCoordinator(hass, entry)

    # Store async_add_entities for dynamic entity management
    coordinator.async_add_entities = async_add_entities

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()
    
    # Only create QModem sensor entities if modem_ctrl is available initially
    if modem_ctrl_available:
        entities = [
            QModemSensor(coordinator, description)
            for description in SENSOR_DESCRIPTIONS
        ]
        async_add_entities(entities, True)
        coordinator.qmodem_entities_created = True
        _LOGGER.info("QModem entities created - modem_ctrl is available")
    else:
        _LOGGER.info("QModem entities not created - modem_ctrl is not available")

    # Register cleanup callbacks
    entry.async_on_unload(coordinator.async_shutdown)

    return coordinator


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

            # First check if modem_ctrl is available
            modem_ctrl_available = False
            try:
                modem_ctrl_list = await self.ubus.list_modem_ctrl()
                modem_ctrl_available = modem_ctrl_list is not None and bool(modem_ctrl_list)
                _LOGGER.debug("Modem_ctrl availability check: %s", modem_ctrl_available)
            except Exception as exc:
                _LOGGER.debug("Modem_ctrl not available: %s", exc)
                modem_ctrl_available = False

            # Try to get QModem info only if modem_ctrl is available
            qmodem_info = None
            qmodem_data_available = False
            if modem_ctrl_available:
                try:
                    qmodem_info = await self.ubus.get_qmodem_info()
                    qmodem_data_available = qmodem_info is not None and bool(qmodem_info.get("info"))
                except Exception as exc:
                    _LOGGER.debug("QModem info not available: %s", exc)
                    qmodem_data_available = False

            _LOGGER.debug("Modem_ctrl available: %s, QModem data available: %s", 
                         modem_ctrl_available, qmodem_data_available)
            if qmodem_info:
                _LOGGER.debug("QModem info received: %s", qmodem_info)

            # Manage qmodem entities dynamically based on modem_ctrl availability
            await self._manage_qmodem_entities(modem_ctrl_available and qmodem_data_available)

            # Process the qmodem data
            if qmodem_info and qmodem_data_available:
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
        """Manage qmodem entities - create when available, remove when not."""
        if self.async_add_entities is None:
            return

        # QModem became available - create entities
        if qmodem_available and not self.qmodem_entities_created:
            _LOGGER.info("QModem/modem_ctrl became available, creating qmodem sensor entities")
            
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

        # QModem became unavailable - remove entities
        elif not qmodem_available and self.qmodem_entities_created:
            _LOGGER.info("QModem/modem_ctrl became unavailable, removing qmodem sensor entities")
            
            # Get entity registry to remove entities
            entity_registry = er.async_get(self.hass)
            
            qmodem_sensors = [
                desc for desc in SENSOR_DESCRIPTIONS 
                if desc.key.startswith("qmodem_")
            ]
            
            removed_count = 0
            for description in qmodem_sensors:
                key_without_prefix = description.key.replace("qmodem_", "")
                unique_id = f"{self.host}_qmodem_{key_without_prefix}"
                existing_entity_id = entity_registry.async_get_entity_id(
                    "sensor", DOMAIN, unique_id
                )
                
                if existing_entity_id:
                    entity_registry.async_remove(existing_entity_id)
                    removed_count += 1
                    _LOGGER.debug("Removed qmodem sensor entity: %s", existing_entity_id)
            
            # Clear tracked entities
            self.qmodem_entities.clear()
            self.qmodem_entities_created = False
            
            if removed_count > 0:
                _LOGGER.info("Removed %d qmodem sensor entities", removed_count)
            else:
                _LOGGER.debug("No qmodem sensor entities to remove")

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
                elif key.startswith("NR5G-"):
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
        """Return True if coordinator is available and qmodem/modem_ctrl is accessible."""
        if not self.coordinator.last_update_success:
            return False
        
        # Check if modem_ctrl is available from the current data update
        # We consider it available if we have any qmodem data
        if not self.coordinator.data:
            return False
            
        # QModem sensor is available if coordinator has data and this sensor has a value
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
