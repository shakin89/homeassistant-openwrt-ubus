"""Support for OpenWrt router sensors with dynamic module loading."""

from __future__ import annotations

import importlib
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Sensor modules to load dynamically
SENSOR_MODULES = [
    "sensors.system_sensor",
    "sensors.qmodem_sensor", 
    "sensors.sta_sensor",
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenWrt sensors from a config entry using dynamic module loading."""
    _LOGGER.info("Setting up OpenWrt sensors with dynamic loading")
    
    coordinators = []
    
    # Dynamically load and setup each sensor module
    for module_name in SENSOR_MODULES:
        try:
            # Import the sensor module
            full_module_name = f"custom_components.{DOMAIN}.{module_name}"
            module = importlib.import_module(full_module_name)
            
            # Check if module has async_setup_entry function
            if hasattr(module, 'async_setup_entry'):
                _LOGGER.debug("Loading sensor module: %s", module_name)
                
                # Call the module's setup function
                coordinator = await module.async_setup_entry(hass, entry, async_add_entities)
                
                if coordinator:
                    coordinators.append(coordinator)
                    _LOGGER.info("Successfully loaded sensor module: %s", module_name)
                else:
                    _LOGGER.debug("Sensor module %s returned no coordinator", module_name)
            else:
                _LOGGER.warning("Sensor module %s has no async_setup_entry function", module_name)
                
        except ImportError as exc:
            _LOGGER.warning("Failed to import sensor module %s: %s", module_name, exc)
        except Exception as exc:
            _LOGGER.error("Error setting up sensor module %s: %s", module_name, exc)
    
    _LOGGER.info("Completed dynamic loading of %d sensor modules", len(coordinators))
    
    # Store coordinators in hass data for cleanup
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    if "coordinators" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["coordinators"] = []
    hass.data[DOMAIN]["coordinators"].extend(coordinators)
