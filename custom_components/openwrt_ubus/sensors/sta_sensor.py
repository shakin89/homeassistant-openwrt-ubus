
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
    UnitOfTime,
    UnitOfInformation
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from ..const import (
    DOMAIN,
    CONF_WIRELESS_SOFTWARE,
    DEFAULT_WIRELESS_SOFTWARE,
)
from ..Ubus import IwinfoUbus

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=2)  # QModem info changes more frequently
# Device statistics sensor descriptions (per connected device)
SENSOR_DESCRIPTIONS = [
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
) -> DeviceStatisticsCoordinator:
    """Set up the device statistics sensors from a config entry."""
    
    # Create and start the coordinator
    coordinator = DeviceStatisticsCoordinator(hass, entry)
    
    # Store the async_add_entities callback in the coordinator for dynamic entity creation
    coordinator.async_add_entities = async_add_entities
    
    # Perform first refresh
    await coordinator.async_config_entry_first_refresh()
    
    # Add initial sensors for any devices already discovered
    initial_entities = []
    if coordinator.data:
        for mac_address in coordinator.data:
            coordinator.known_devices.add(mac_address)
            for description in SENSOR_DESCRIPTIONS:
                initial_entities.append(
                    DeviceStatisticsSensor(coordinator, description, mac_address)
                )
    
    # Add initial entities if any
    if initial_entities:
        async_add_entities(initial_entities, True)
        _LOGGER.info("Set up %d initial device statistics sensors", len(initial_entities))
    
    # Register shutdown callback
    def shutdown_coordinator():
        """Shutdown coordinator on Home Assistant stop."""
        hass.async_create_task(coordinator.async_shutdown())
    
    entry.async_on_unload(shutdown_coordinator)
    
    # Return the coordinator for the main sensor module to track
    return coordinator


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
                        for description in SENSOR_DESCRIPTIONS:
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
