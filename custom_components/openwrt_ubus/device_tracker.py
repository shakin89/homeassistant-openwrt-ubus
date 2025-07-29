"""Support for OpenWrt device tracking via ubus."""

from __future__ import annotations

from datetime import timedelta
import logging

import voluptuous as vol

from homeassistant.components.device_tracker import (
    PLATFORM_SCHEMA as DEVICE_TRACKER_PLATFORM_SCHEMA,
    ScannerEntity,
    SourceType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_DHCP_SOFTWARE,
    CONF_WIRELESS_SOFTWARE,
    DEFAULT_DHCP_SOFTWARE,
    DEFAULT_WIRELESS_SOFTWARE,
    DHCP_SOFTWARES,
    DOMAIN,
    WIRELESS_SOFTWARES,
)
from .Ubus import HostapdUbus, IwinfoUbus

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)

PLATFORM_SCHEMA = DEVICE_TRACKER_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Optional(CONF_WIRELESS_SOFTWARE, default=DEFAULT_WIRELESS_SOFTWARE): vol.In(
            WIRELESS_SOFTWARES
        ),
        vol.Optional(CONF_DHCP_SOFTWARE, default=DEFAULT_DHCP_SOFTWARE): vol.In(
            DHCP_SOFTWARES
        ),
    }
)
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device tracker from a config entry."""
    coordinator = OpenwrtDataUpdateCoordinator(hass, entry)

    # Store the async_add_entities callback for dynamic device addition
    coordinator.async_add_entities = async_add_entities

    # Initialize known_devices from existing entity registry entries
    await coordinator._restore_known_devices_from_registry()
    _LOGGER.debug("Restored %d known devices from registry", len(coordinator.known_devices))

    # Fetch initial data so we have data when entities subscribe
    # Don't raise ConfigEntryNotReady here since connection was already tested in __init__.py
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as exc:
        # If initial refresh fails, just log it and continue
        # The coordinator will handle retries automatically
        _LOGGER.warning("Initial data fetch failed, will retry automatically: %s", exc)

    # Create device tracker entities for each detected device
    if coordinator.data and isinstance(coordinator.data, dict) and coordinator.data:
        _LOGGER.info("Initial scan found %d devices", len(coordinator.data))
        # Normalize MAC addresses to uppercase for consistency
        device_macs = {mac.upper() for mac in coordinator.data.keys()}
        _LOGGER.debug("Initial devices detected: %s", device_macs)
        _LOGGER.debug("Known devices before creation: %s", coordinator.known_devices)
        
        new_entities = await coordinator._create_entities_for_devices(device_macs)
        if new_entities:
            async_add_entities(new_entities, True)
            _LOGGER.info("Created %d initial device tracker entities", len(new_entities))
        else:
            _LOGGER.info("No new entities to create (all devices already exist)")
    else:
        _LOGGER.info("No devices found in initial scan, entities will be created dynamically as devices are discovered")

    # Register cleanup callback for when the entry is unloaded
    entry.async_on_unload(coordinator.async_shutdown)

    # Start the coordinator update cycle
    await coordinator.async_request_refresh()

class OpenwrtDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the router."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.connected_devices = {}
        self.entry = entry
        self.host = entry.data[CONF_HOST]
        self.username = entry.data[CONF_USERNAME]
        self.password = entry.data[CONF_PASSWORD]
        self.wireless_sw = entry.data.get(CONF_WIRELESS_SOFTWARE, DEFAULT_WIRELESS_SOFTWARE)
        self.dhcp_sw = entry.data.get(CONF_DHCP_SOFTWARE, DEFAULT_DHCP_SOFTWARE)

        # Get Home Assistant's HTTP client session
        session = async_get_clientsession(hass)

        self.url = f"http://{self.host}/ubus"
        if self.wireless_sw == "hostapd":
            self.ubus = HostapdUbus(self.url, self.username, self.password, session=session)
        else:
            self.ubus = IwinfoUbus(self.url, self.username, self.password, session=session)

        self.ap_devices = []
        self.mac2name = {}
        self.known_devices = set()  # Track known devices
        self.async_add_entities = None  # Will be set in async_setup_entry

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.host}",
            update_interval=SCAN_INTERVAL,
        )

        # Initialize with empty data to avoid None issues
        self.data = {}

        # Create router device info for linking client devices
        self._router_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.host)},
            name=f"OpenWrt Router ({self.host})",
            manufacturer="OpenWrt",
            model="Router",
            configuration_url=f"http://{self.host}",
        )

    async def async_shutdown(self):
        """Shutdown the coordinator and close connections."""
        try:
            await self.ubus.close()
        except Exception as exc:
            _LOGGER.debug("Error closing ubus connection: %s", exc)

    async def _restore_known_devices_from_registry(self) -> None:
        """Restore known devices from existing entity registry entries."""
        entity_registry = er.async_get(self.hass)
        existing_entities = er.async_entries_for_config_entry(entity_registry, self.entry.entry_id)
        for entity_entry in existing_entities:
            if entity_entry.domain == "device_tracker" and entity_entry.platform == DOMAIN:
                # Extract MAC address from unique_id (format: "{host}_{mac_address}")
                if entity_entry.unique_id and "_" in entity_entry.unique_id:
                    mac_address = entity_entry.unique_id.split("_", 1)[1].upper()  # Normalize to uppercase
                    self.known_devices.add(mac_address)
                    _LOGGER.debug("Restored known device from registry: %s", mac_address)

    async def _create_entities_for_devices(self, mac_addresses: set[str]) -> list:
        """Create device tracker entities for the given MAC addresses."""
        entity_registry = er.async_get(self.hass)
        new_entities = []
        
        for mac_address in mac_addresses:
            # Normalize MAC address format to ensure consistency
            mac_address = mac_address.upper()
            
            # Skip if already in known devices
            if mac_address in self.known_devices:
                _LOGGER.debug("Device %s already in known devices, skipping", mac_address)
                continue
                
            # Check if entity already exists in registry
            unique_id = f"{self.host}_{mac_address}"
            existing_entity_id = entity_registry.async_get_entity_id(
                "device_tracker", DOMAIN, unique_id
            )
            
            if existing_entity_id:
                _LOGGER.debug(
                    "Device tracker entity %s already exists with entity_id %s, adding to known devices",
                    unique_id, existing_entity_id
                )
                # Add to known devices to prevent repeated checks
                self.known_devices.add(mac_address)
                continue
            
            # Create device tracker entity for the new device
            try:
                entity = OpenwrtDeviceTracker(self, mac_address)
                # Ensure the entity is enabled by default
                entity._attr_entity_registry_enabled_default = True
                new_entities.append(entity)
                self.known_devices.add(mac_address)
                _LOGGER.debug("Created device tracker entity for %s with unique_id %s", mac_address, unique_id)
            except Exception as exc:
                _LOGGER.error("Failed to create entity for device %s: %s", mac_address, exc)
                continue
        
        return new_entities

    async def _async_update_data(self):
        """Update data via library."""
        try:
            connected_devices = await self._update_data()
            self.connected_devices = connected_devices
            
            # Check for new devices and add them
            if self.async_add_entities is not None and connected_devices:
                # Normalize MAC addresses to uppercase for consistency
                current_devices = {mac.upper() for mac in connected_devices.keys()}
                new_devices = current_devices - self.known_devices
                if new_devices:
                    _LOGGER.info("Found %d new devices: %s", len(new_devices), new_devices)
                    new_entities = await self._create_entities_for_devices(new_devices)
                    if new_entities:
                        self.async_add_entities(new_entities, True)
                        _LOGGER.info("Added %d new device tracker entities", len(new_entities))

            _LOGGER.debug("Returning connected devices data: %s", connected_devices)
            return connected_devices
        except Exception as exception:
            raise UpdateFailed(exception) from exception

    async def _update_data(self):
        """Fetch data from router."""
        _LOGGER.debug("Starting device scan for %s", self.host)

        # Set flag to indicate we're in an update cycle
        self._currently_updating = True

        try:
            # Ensure connection
            try:
                if await self.ubus.connect() is None:
                    raise UpdateFailed("Failed to connect to router")
            except Exception as exc:
                raise UpdateFailed(f"Connection failed: {exc}") from exc

            # Get AP devices if not already retrieved
            if not self.ap_devices:
                try:
                    ap_devices_result = await self._get_ap_devices()
                    if ap_devices_result:
                        self.ap_devices.extend(ap_devices_result)
                        _LOGGER.info("Found %d AP devices: %s", len(self.ap_devices), self.ap_devices)
                    else:
                        _LOGGER.warning("No AP devices found")
                except Exception as exc:
                    _LOGGER.warning("Failed to get AP devices: %s", exc)
                    # Continue without AP devices, may work with cached data

            # Generate MAC to name mapping before processing devices
            if not self.mac2name:
                try:
                    await self._generate_mac2name()
                except Exception as exc:
                    _LOGGER.warning("Failed to generate MAC to name mapping: %s", exc)

            # Get connected devices
            connected_devices = {}
            total_devices_found = 0

            for ap_device in self.ap_devices:
                try:
                    _LOGGER.debug("Scanning AP device: %s", ap_device)
                    sta_devices = await self._get_sta_devices(ap_device)
                    if sta_devices:
                        _LOGGER.debug("Found %d connected devices on %s: %s", len(sta_devices), ap_device, sta_devices)
                        total_devices_found += len(sta_devices)

                        for mac in sta_devices:
                            # Normalize MAC address to uppercase for consistency
                            normalized_mac = mac.upper()
                            connected_devices[normalized_mac] = {
                                "mac": normalized_mac,
                                "hostname": self._get_device_name(normalized_mac),
                                "ap_device": ap_device,
                                "connected": True,
                                "ip_address": self._get_device_ip(normalized_mac),
                            }
                    else:
                        _LOGGER.debug("No devices found on AP: %s", ap_device)
                except Exception as exc:
                    _LOGGER.warning("Failed to get station devices for %s: %s", ap_device, exc)
                    continue

            _LOGGER.debug("Total connected devices found: %d", total_devices_found)
            return connected_devices

        finally:
            # Clear the update flag
            self._currently_updating = False

    async def _get_ap_devices(self):
        ap_devices_result = self.ubus.parse_ap_devices(await self.ubus.get_ap_devices())
        return ap_devices_result

    async def _get_sta_devices(self, device):
        """Get station devices for a specific AP device."""
        sta_devices_result = self.ubus.parse_sta_devices(await self.ubus.get_sta_devices(device))
        return sta_devices_result

    def _get_device_ip(self, mac_address):
        """Get device IP address."""
        if self.mac2name and mac_address.upper() in self.mac2name:
            return self.mac2name[mac_address.upper()].get("ip", "Unknown IP")

    def _get_device_name(self, mac_address):
        """Get device name from MAC address."""
        # Use the mac2name mapping if available
        if self.mac2name and mac_address.upper() in self.mac2name:
            return self.mac2name[mac_address.upper()].get("hostname", mac_address)

        # Fallback to MAC address if no name found
        return mac_address.replace(":", "")


    async def _generate_mac2name(self):
        """Generate MAC to name mapping based on DHCP server."""
        self.mac2name = {}

        if self.dhcp_sw == "dnsmasq":
            await self._generate_dnsmasq_mac2name()
        elif self.dhcp_sw == "odhcpd":
            await self._generate_odhcpd_mac2name()

    async def _generate_dnsmasq_mac2name(self):
        """Generate MAC to name mapping for dnsmasq."""
        try:
            if result := await self.ubus.get_uci_config("dhcp", "dnsmasq"):
                values = result["values"].values()
                self.leasefile = next(iter(values))["leasefile"]
            else:
                return
            lease_result = await self.ubus.file_read(self.leasefile)
            if lease_result:
                for line in lease_result["data"].splitlines():
                    hosts = line.split(" ")
                    if len(hosts) >= 4:
                        self.mac2name[hosts[1].upper()] = { "hostname": hosts[3], "ip": hosts[2] }
        except Exception as err:
            _LOGGER.warning("Failed to get dnsmasq leases: %s", err)

    async def _generate_odhcpd_mac2name(self):
        """Generate MAC to name mapping for odhcpd."""
        try:
            result = await self.ubus.get_dhcp_method("ipv4leases")
            if result:
                for device in result["device"].values():
                    for lease in device["leases"]:
                        mac = lease["mac"]  # mac = aabbccddeeff
                        # Convert it to expected format with colon
                        mac = ":".join(mac[i : i + 2] for i in range(0, len(mac), 2))
                        self.mac2name[mac.upper()] = { "hostname": lease["hostname"] , "ip": lease["ip"] }
        except Exception as err:
            _LOGGER.warning("Failed to get odhcpd leases: %s", err)

class OpenwrtDeviceTracker(CoordinatorEntity, ScannerEntity):
    """Representation of a device tracker entity."""

    def __init__(self, coordinator: OpenwrtDataUpdateCoordinator, mac_address: str) -> None:
        """Initialize the device tracker."""
        super().__init__(coordinator)
        self.mac_address = mac_address
        self.ap_device = coordinator.data.get(mac_address, {}).get("ap_device", coordinator.connected_devices.get(mac_address, {}).get("ap_device", "Unknown AP"))
        self.router = coordinator.host or "Unknown Router"
        self._attr_unique_id = f"{coordinator.host}_{mac_address}"
        self._attr_name = None  # Will be set dynamically
        self._attr_entity_registry_enabled_default = True  # Enable by default

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info with updated device name."""
        device_name = self._get_device_name()
        return DeviceInfo(
            identifiers={(DOMAIN, self.mac_address)},
            name=device_name,
            model="Network Device",
            connections={("mac", self.mac_address)},
            via_device=(DOMAIN, self.coordinator.host),
        )

    def _get_device_name(self) -> str:
        """Get the device name from coordinator data or fallback to MAC."""
        connected_router = self.coordinator.host or "Unknown Router"
        base_name = f"{connected_router}({self.ap_device})"
        if self.ap_device == "Unknown AP":
            base_name = f"{connected_router}"
        
        # First try to get hostname from coordinator data (check both original and normalized MAC)
        device_data = (self.coordinator.data.get(self.mac_address) or 
                      self.coordinator.data.get(self.mac_address.upper()))
        if device_data:
            hostname = device_data.get("hostname")
            if hostname and hostname != self.mac_address and hostname != self.mac_address.upper():
                return f"{base_name} {hostname}"
        
        # Then try to get from mac2name mapping
        if self.coordinator.mac2name and self.mac_address.upper() in self.coordinator.mac2name:
            hostname = self.coordinator.mac2name[self.mac_address.upper()].get("hostname")
            if hostname:
                return f"{base_name} {hostname}"
        
        # Fallback to MAC address if no name found
        return f"{base_name} {self.mac_address.replace(":", "")}"



    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self._get_device_name()

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device."""
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        """Return true if the device is connected to the network."""
        # Check both the original MAC and normalized (uppercase) MAC for compatibility
        connected = (self.mac_address in self.coordinator.data or 
                    self.mac_address.upper() in self.coordinator.data)
        _LOGGER.debug("Device %s connection status: %s", self.mac_address, connected)
        return connected

    @property
    def available(self) -> bool:
        """Return True if coordinator is available."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the device state attributes."""
        attributes = {
            "host": self.coordinator.host,
            "mac": self.mac_address,
        }

        # Check both original and normalized MAC address for device info
        device_info = (self.coordinator.data.get(self.mac_address) or 
                      self.coordinator.data.get(self.mac_address.upper()))
        
        if device_info:
            attributes.update({
                "name": self._get_device_name(),
                "ap_device": device_info.get("ap_device"),
                "hostname": device_info.get("hostname", self.mac_address),
                "connection_type": "wireless",
                "router": self.coordinator.host,
                "host": device_info.get("ip_address"),
            })
        else:
            attributes.update({
                "last_seen": "disconnected",
                "connection_type": "wireless",
            })

        return attributes
