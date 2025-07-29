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
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
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
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenWrt system sensors from a config entry."""
    # Create system info coordinator
    coordinator = SystemInfoCoordinator(hass, entry)

    # Store async_add_entities for dynamic entity management
    coordinator.async_add_entities = async_add_entities

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()
    
    # Create system sensor entities
    entities = [
        SystemInfoSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities, True)

    # Register cleanup callbacks
    entry.async_on_unload(coordinator.async_shutdown)

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

            # Process the data
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
