"""Device kick button for OpenWrt Ubus integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.exceptions import HomeAssistantError

from ..const import DOMAIN, CONF_TRACKING_METHOD, DEFAULT_TRACKING_METHOD
from ..shared_data_manager import SharedDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device kick buttons for OpenWrt."""
    _LOGGER.info("Setting up OpenWrt device kick buttons")
    tracking_method = entry.data.get(CONF_TRACKING_METHOD, DEFAULT_TRACKING_METHOD)
    
    # Get shared data manager
    data_manager_key = f"data_manager_{entry.entry_id}"
    data_manager = hass.data[DOMAIN][data_manager_key]
    
    # Create coordinator for device kick buttons - we need device_statistics, ap_info, and hostapd_available
    from datetime import timedelta
    coordinator = SharedDataUpdateCoordinator(
        hass,
        data_manager,
        ["device_statistics", "ap_info", "hostapd_available"],  # Data types this coordinator needs
        f"{DOMAIN}_device_kick_{entry.data['host']}",
        timedelta(seconds=30),  # Update every 30 seconds
    )
    
    # Store coordinator in hass data for later reference
    hass.data.setdefault(DOMAIN, {})
    coordinators_key = f"device_kick_coordinators"
    if coordinators_key not in hass.data[DOMAIN]:
        hass.data[DOMAIN][coordinators_key] = {}
    hass.data[DOMAIN][coordinators_key][entry.entry_id] = coordinator
    
    # Track created buttons to avoid duplicates and allow re-enabling
    created_buttons = set()
    button_entities = {}  # Store references to button entities for availability updates
    
    @callback
    def _async_add_kick_buttons():
        """Add kick buttons for connected devices and update availability."""
        _LOGGER.debug("Checking for devices to create kick buttons and update availability")

        # Get current data
        hostapd_available = coordinator.data.get("hostapd_available", False)
        ap_info_data = coordinator.data.get("ap_info", {})
        device_statistics = coordinator.data.get("device_statistics", {})

        # Get host for unique ID generation
        host = entry.data["host"]

        # Log current state for debugging
        _LOGGER.debug("Hostapd available: %s, AP info available: %s, Device stats count: %d",
                     hostapd_available, bool(ap_info_data), len(device_statistics))

        new_buttons = []
        current_devices = set()

        # Process each connected device (even if hostapd is not available, we still track them)
        for mac, device_info in device_statistics.items():
            if not isinstance(device_info, dict):
                continue

            ap_device = device_info.get("ap_device")
            if not ap_device:
                continue

            # Create unique identifier for this device button - use only host+mac (no AP)
            # This allows the button to follow the device when it moves between APs
            button_id = f"{host}_{mac.replace(':', '_')}"
            current_devices.add(button_id)

            # Get SSID for user-friendly naming
            ap_ssid = device_info.get("ap_ssid", ap_device)

            # Create button if it doesn't exist (regardless of current availability)
            if button_id not in created_buttons:
                # Create new kick button
                kick_button = DeviceKickButton(
                    coordinator=coordinator,
                    device_mac=mac,
                    device_name=device_info.get("hostname", f"Device {mac}"),
                    unique_id=button_id,
                    host=host
                )

                new_buttons.append(kick_button)
                created_buttons.add(button_id)
                button_entities[button_id] = kick_button
                _LOGGER.debug("Created kick button for device %s (%s) on AP %s (%s)",
                             device_info.get("hostname", mac), mac, ap_ssid, ap_device)
        
        # Add new buttons if any
        if new_buttons:
            async_add_entities(new_buttons)
            _LOGGER.info("Added %d new device kick buttons", len(new_buttons))
        
        # Update availability for all existing buttons
        for button_id, button_entity in button_entities.items():
            # Only update state if the entity has been fully initialized (hass is set)
            if hasattr(button_entity, 'hass') and button_entity.hass is not None:
                try:
                    # Trigger availability update by writing state
                    button_entity.async_write_ha_state()
                except RuntimeError as exc:
                    _LOGGER.debug("Could not update state for button %s: %s", button_id, exc)
        
        # Clean up tracking for completely disconnected devices
        disconnected_devices = created_buttons - current_devices
        if disconnected_devices:
            _LOGGER.debug("Found %d disconnected devices, removing from tracking", 
                         len(disconnected_devices))
            for button_id in disconnected_devices:
                created_buttons.discard(button_id)
                button_entities.pop(button_id, None)
    
    # Initial setup
    await coordinator.async_config_entry_first_refresh()
    _async_add_kick_buttons()
    
    # Listen for coordinator updates to refresh buttons
    coordinator.async_add_listener(_async_add_kick_buttons)
    
    # Return None to indicate we don't need tracking in button.py
    return None


class DeviceKickButton(CoordinatorEntity[SharedDataUpdateCoordinator], ButtonEntity):
    """Button to kick a device from AP."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SharedDataUpdateCoordinator,
        device_mac: str,
        device_name: str,
        unique_id: str,
        host: str,
    ) -> None:
        """Initialize the kick button."""
        super().__init__(coordinator)

        self._device_mac = device_mac
        self._initial_device_name = device_name
        self._host = host
        self._previous_available_state = None  # Track availability changes
        self._previous_ap_info = None  # Track AP changes: (host, ap_device, ssid)

        self._attr_unique_id = f"{DOMAIN}_{unique_id}_kick"

    def _get_device_info(self) -> dict:
        """Get current device info from coordinator data."""
        device_statistics = self.coordinator.data.get("device_statistics", {})
        return device_statistics.get(self._device_mac, {})

    @property
    def name(self) -> str:
        """Return the name of the button using SSID."""
        device_info = self._get_device_info()
        device_name = device_info.get("hostname", self._initial_device_name)
        ap_ssid = device_info.get("ap_ssid", "Unknown Network")

        if device_name == "Unknown" or device_name == "*" or device_name == self._device_mac:
            return f"Kick {self._device_mac} from {ap_ssid}"
        else:
            return f"Kick {device_name} from {ap_ssid}"

    @property
    def device_info(self):
        """Return device info - associate with current AP device."""
        from homeassistant.helpers.device_registry import DeviceInfo
        device_info = self._get_device_info()
        ap_device = device_info.get("ap_device", "unknown")

        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._host}_ap_{ap_device}")},
        )

    @property
    def available(self) -> bool:
        """Return if button is available."""
        if not super().available:
            _LOGGER.debug("Button %s: Coordinator not available", self._attr_unique_id)
            current_state = False
        else:
            # Check if hostapd is available
            hostapd_available = self.coordinator.data.get("hostapd_available", False)
            if not hostapd_available:
                _LOGGER.debug("Button %s: Hostapd not available", self._attr_unique_id)
                current_state = False
            else:
                # Check if device is still connected
                device_info = self._get_device_info()
                is_connected = device_info.get("connected", False)
                current_ap_device = device_info.get("ap_device")
                current_ssid = device_info.get("ap_ssid", "Unknown")

                if not is_connected:
                    _LOGGER.debug("Button %s: Device %s not connected", self._attr_unique_id, self._device_mac)
                    current_state = False
                elif not current_ap_device:
                    _LOGGER.debug("Button %s: Device %s has no AP info", self._attr_unique_id, self._device_mac)
                    current_state = False
                else:
                    # Track AP changes using router host + interface + SSID
                    current_ap_info = (self._host, current_ap_device, current_ssid)
                    _LOGGER.debug("Current_ap_info: %s %s %s", self._host, current_ap_device, current_ssid)

                    if self._previous_ap_info and self._previous_ap_info != current_ap_info:
                        prev_host, prev_device, prev_ssid = self._previous_ap_info
                        _LOGGER.info(
                            "Button %s: Device %s moved from %s/%s (%s) to %s/%s (%s)",
                            self._attr_unique_id, self._device_mac,
                            prev_host, prev_device, prev_ssid,
                            self._host, current_ap_device, current_ssid
                        )

                    self._previous_ap_info = current_ap_info
                    _LOGGER.debug("Button %s: Available - device %s connected on %s/%s (%s)",
                                 self._attr_unique_id, self._device_mac,
                                 self._host, current_ap_device, current_ssid)
                    current_state = True

        # Log availability state changes
        if self._previous_available_state is not None and self._previous_available_state != current_state:
            if current_state:
                _LOGGER.info("Button %s: Device %s became available (reconnected or hostapd restored)",
                           self._attr_unique_id, self._device_mac)
            else:
                _LOGGER.info("Button %s: Device %s became unavailable (disconnected or hostapd down)",
                           self._attr_unique_id, self._device_mac)

        self._previous_available_state = current_state
        return current_state
    
    @property
    def icon(self) -> str:
        """Return the icon for the button."""
        return "mdi:wifi-cancel"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        device_info = self._get_device_info()
        ap_device = device_info.get("ap_device", "Unknown AP")
        ap_ssid = device_info.get("ap_ssid", "Unknown Network")
        hostname = device_info.get("hostname", self._initial_device_name)

        return {
            "device_mac": self._device_mac,
            "device_name": hostname,
            "router": self._host,
            "ap_device": ap_device,
            "ap_ssid": ap_ssid,
            "hostapd_interface": f"hostapd.{ap_device}",
        }
    
    async def async_press(self) -> None:
        """Press the button to kick the device."""
        try:
            # Get current device info
            device_info = self._get_device_info()
            ap_device = device_info.get("ap_device")
            ap_ssid = device_info.get("ap_ssid", ap_device)
            hostname = device_info.get("hostname", self._initial_device_name)

            if not ap_device:
                raise HomeAssistantError(f"Cannot kick device {hostname}: no AP information available")

            hostapd_interface = f"hostapd.{ap_device}"

            _LOGGER.info("Kicking device %s (%s) from %s/%s (%s)",
                        hostname, self._device_mac, self._host, ap_device, ap_ssid)

            # Get the ubus client
            ubus = await self.coordinator.data_manager.get_ubus_connection_async()

            # Kick the device
            await ubus.kick_device(
                hostapd_interface=hostapd_interface,
                mac_address=self._device_mac,
                ban_time=60000,  # 60 seconds
                reason=5  # Deauth reason
            )

            _LOGGER.info("Successfully kicked device %s from %s (%s)",
                        self._device_mac, self._host, ap_ssid)

            # Refresh data to update device status
            await self.coordinator.async_request_refresh()

        except Exception as exc:
            device_info = self._get_device_info()
            hostname = device_info.get("hostname", self._initial_device_name)
            _LOGGER.error("Failed to kick device %s: %s", self._device_mac, exc)
            raise HomeAssistantError(f"Failed to kick device {hostname}: {exc}") from exc
