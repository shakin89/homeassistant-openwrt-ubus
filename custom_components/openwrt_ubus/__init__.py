"""The ubus component for OpenWrt."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_DHCP_SOFTWARE,
    CONF_WIRELESS_SOFTWARE,
    DEFAULT_DHCP_SOFTWARE,
    DEFAULT_WIRELESS_SOFTWARE,
    DHCP_SOFTWARES,
    DOMAIN,
    PLATFORMS,
    WIRELESS_SOFTWARES,
)
from .Ubus import Ubus

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_WIRELESS_SOFTWARE, default=DEFAULT_WIRELESS_SOFTWARE): vol.In(
                    WIRELESS_SOFTWARES
                ),
                vol.Optional(CONF_DHCP_SOFTWARE, default=DEFAULT_DHCP_SOFTWARE): vol.In(
                    DHCP_SOFTWARES
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the openwrt ubus component."""
    if DOMAIN not in config:
        return True

    hass.data.setdefault(DOMAIN, {})

    # Store the configuration for the device tracker
    hass.data[DOMAIN]["config"] = config[DOMAIN]

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up openwrt ubus from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Test connection before setting up platforms
    try:
        url = f"http://{entry.data[CONF_HOST]}/ubus"
        session = async_get_clientsession(hass)
        ubus = Ubus(url, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD], session=session)

        # Test connection
        session_id = await ubus.connect()
        if session_id is None:
            raise ConfigEntryNotReady(f"Failed to connect to OpenWrt device at {entry.data[CONF_HOST]}")

        # Check for modem_ctrl availability and store the result
        modem_ctrl_available = False
        try:
            modem_ctrl_list = await ubus.list_modem_ctrl()
            modem_ctrl_available = modem_ctrl_list is not None and bool(modem_ctrl_list)
            _LOGGER.debug("Modem_ctrl availability check: %s", modem_ctrl_available)
        except Exception as exc:
            _LOGGER.debug("Modem_ctrl not available: %s", exc)
            modem_ctrl_available = False

        # Store modem_ctrl availability in hass data
        hass.data[DOMAIN]["modem_ctrl_available"] = modem_ctrl_available

    except Exception as exc:
        raise ConfigEntryNotReady(f"Failed to connect to OpenWrt device at {entry.data[CONF_HOST]}: {exc}") from exc

    # Store the config entry data
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up coordinators
        if DOMAIN in hass.data and "coordinators" in hass.data[DOMAIN]:
            coordinators = hass.data[DOMAIN]["coordinators"]
            for coordinator in coordinators:
                if hasattr(coordinator, 'async_shutdown'):
                    try:
                        await coordinator.async_shutdown()
                    except Exception as exc:
                        _LOGGER.debug("Error shutting down coordinator: %s", exc)
            # Clear the coordinators list
            hass.data[DOMAIN]["coordinators"] = []
        
        # Clean up entry-specific data
        hass.data[DOMAIN].pop(entry.entry_id, None)
        
        # Clean up modem_ctrl availability data if no more entries
        if len([e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]) == 0:
            hass.data[DOMAIN].pop("modem_ctrl_available", None)

    return unload_ok
