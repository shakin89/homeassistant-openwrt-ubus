"""Support for OpenWrt router sensors."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .sensors import system_sensor, qmodem_sensor, sta_sensor

_LOGGER = logging.getLogger(__name__)

# Sensor modules to setup
SENSOR_MODULES = [
    system_sensor,
    qmodem_sensor, 
    sta_sensor,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenWrt sensors from a config entry."""
    _LOGGER.info("Setting up OpenWrt sensors")
    
    coordinators = []
    
    # Setup each sensor module
    for module in SENSOR_MODULES:
        try:
            # Check if module has async_setup_entry function
            if hasattr(module, 'async_setup_entry'):
                module_name = module.__name__.split('.')[-1]
                _LOGGER.debug("Loading sensor module: %s", module_name)
                
                # Call the module's setup function
                coordinator = await module.async_setup_entry(hass, entry, async_add_entities)
                
                if coordinator:
                    coordinators.append(coordinator)
                    _LOGGER.info("Successfully loaded sensor module: %s", module_name)
                else:
                    module_name = module.__name__.split('.')[-1]
                    _LOGGER.debug("Sensor module %s returned no coordinator", module_name)
            else:
                module_name = module.__name__.split('.')[-1]
                _LOGGER.warning("Sensor module %s has no async_setup_entry function", module_name)
                
        except Exception as exc:
            module_name = getattr(module, '__name__', 'unknown').split('.')[-1]
            _LOGGER.error("Error setting up sensor module %s: %s", module_name, exc)
    
    _LOGGER.info("Completed loading of %d sensor modules", len(coordinators))
    
    # Store coordinators in hass data for cleanup
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    if "coordinators" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["coordinators"] = []
    hass.data[DOMAIN]["coordinators"].extend(coordinators)
