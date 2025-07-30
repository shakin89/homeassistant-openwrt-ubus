"""Config flow for openwrt ubus integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DHCP_SOFTWARE,
    CONF_WIRELESS_SOFTWARE,
    CONF_ENABLE_QMODEM_SENSORS,
    CONF_ENABLE_STA_SENSORS,
    CONF_ENABLE_SYSTEM_SENSORS,
    CONF_ENABLE_AP_SENSORS,
    CONF_SYSTEM_SENSOR_TIMEOUT,
    CONF_QMODEM_SENSOR_TIMEOUT,
    CONF_STA_SENSOR_TIMEOUT,
    CONF_AP_SENSOR_TIMEOUT,
    DEFAULT_DHCP_SOFTWARE,
    DEFAULT_WIRELESS_SOFTWARE,
    DEFAULT_ENABLE_QMODEM_SENSORS,
    DEFAULT_ENABLE_STA_SENSORS,
    DEFAULT_ENABLE_SYSTEM_SENSORS,
    DEFAULT_ENABLE_AP_SENSORS,
    DEFAULT_SYSTEM_SENSOR_TIMEOUT,
    DEFAULT_QMODEM_SENSOR_TIMEOUT,
    DEFAULT_STA_SENSOR_TIMEOUT,
    DEFAULT_AP_SENSOR_TIMEOUT,
    DHCP_SOFTWARES,
    DOMAIN,
    WIRELESS_SOFTWARES,
)
from .Ubus import Ubus

_LOGGER = logging.getLogger(__name__)

# Step 1: Connection configuration
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_WIRELESS_SOFTWARE, default=DEFAULT_WIRELESS_SOFTWARE): vol.In(
            WIRELESS_SOFTWARES
        ),
        vol.Optional(CONF_DHCP_SOFTWARE, default=DEFAULT_DHCP_SOFTWARE): vol.In(
            DHCP_SOFTWARES
        ),
    }
)

# Step 2: Sensor configuration
STEP_SENSORS_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENABLE_SYSTEM_SENSORS, default=DEFAULT_ENABLE_SYSTEM_SENSORS): bool,
        vol.Optional(CONF_ENABLE_QMODEM_SENSORS, default=DEFAULT_ENABLE_QMODEM_SENSORS): bool,
        vol.Optional(CONF_ENABLE_STA_SENSORS, default=DEFAULT_ENABLE_STA_SENSORS): bool,
        vol.Optional(CONF_ENABLE_AP_SENSORS, default=DEFAULT_ENABLE_AP_SENSORS): bool,
    }
)

# Step 3: Timeout configuration
STEP_TIMEOUTS_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SYSTEM_SENSOR_TIMEOUT, default=DEFAULT_SYSTEM_SENSOR_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=300)
        ),
        vol.Optional(CONF_QMODEM_SENSOR_TIMEOUT, default=DEFAULT_QMODEM_SENSOR_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=30, max=600)
        ),
        vol.Optional(CONF_STA_SENSOR_TIMEOUT, default=DEFAULT_STA_SENSOR_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=300)
        ),
        vol.Optional(CONF_AP_SENSOR_TIMEOUT, default=DEFAULT_AP_SENSOR_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=30, max=600)
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # Get Home Assistant's HTTP client session
    session = async_get_clientsession(hass)
    
    url = f"http://{data[CONF_HOST]}/ubus"
    ubus = Ubus(url, data[CONF_USERNAME], data[CONF_PASSWORD], session=session)
    
    try:
        # Test connection
        session_id = await ubus.connect()
        if session_id is None:
            raise CannotConnect("Failed to connect to OpenWrt device")

    except Exception as exc:
        _LOGGER.exception("Unexpected exception during connection test")
        raise CannotConnect("Failed to connect to OpenWrt device") from exc
    finally:
        # Always close the session to prevent leaks
        await ubus.close()

    # Return info that you want to store in the config entry.
    return {"title": f"OpenWrt ubus {data[CONF_HOST]}"}


class OpenwrtUbusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for openwrt ubus."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._connection_data: dict[str, Any] = {}
        self._sensor_data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return OpenwrtUbusOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Check if already configured
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()

                # Store connection data and proceed to sensor configuration
                self._connection_data = user_input
                return await self.async_step_sensors()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the sensor configuration step."""
        if user_input is not None:
            self._sensor_data = user_input
            return await self.async_step_timeouts()

        return self.async_show_form(
            step_id="sensors",
            data_schema=STEP_SENSORS_DATA_SCHEMA,
            description_placeholders={
                "host": self._connection_data[CONF_HOST]
            }
        )

    async def async_step_timeouts(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the timeout configuration step."""
        if user_input is not None:
            # Combine all configuration data
            config_data = {
                **self._connection_data,
                **self._sensor_data,
                **user_input,
            }
            
            info = {"title": f"OpenWrt ubus {config_data[CONF_HOST]}"}
            return self.async_create_entry(title=info["title"], data=config_data)

        return self.async_show_form(
            step_id="timeouts",
            data_schema=STEP_TIMEOUTS_DATA_SCHEMA,
            description_placeholders={
                "host": self._connection_data[CONF_HOST]
            }
        )


class OpenwrtUbusOptionsFlow(OptionsFlow):
    """Handle options flow for OpenWrt ubus."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            # Get current data and merge with new options
            new_data = dict(self.config_entry.data)
            new_data.update(user_input)
            
            # Update the config entry with new data
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            
            # Reload the integration to apply changes
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            
            return self.async_create_entry(title="", data={})

        # Create form with all configurable options
        current_data = self.config_entry.data
        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_WIRELESS_SOFTWARE,
                    default=current_data.get(CONF_WIRELESS_SOFTWARE, DEFAULT_WIRELESS_SOFTWARE)
                ): vol.In(WIRELESS_SOFTWARES),
                vol.Optional(
                    CONF_DHCP_SOFTWARE,
                    default=current_data.get(CONF_DHCP_SOFTWARE, DEFAULT_DHCP_SOFTWARE)
                ): vol.In(DHCP_SOFTWARES),
                vol.Optional(
                    CONF_ENABLE_SYSTEM_SENSORS,
                    default=current_data.get(CONF_ENABLE_SYSTEM_SENSORS, DEFAULT_ENABLE_SYSTEM_SENSORS)
                ): bool,
                vol.Optional(
                    CONF_ENABLE_QMODEM_SENSORS,
                    default=current_data.get(CONF_ENABLE_QMODEM_SENSORS, DEFAULT_ENABLE_QMODEM_SENSORS)
                ): bool,
                vol.Optional(
                    CONF_ENABLE_STA_SENSORS,
                    default=current_data.get(CONF_ENABLE_STA_SENSORS, DEFAULT_ENABLE_STA_SENSORS)
                ): bool,
                vol.Optional(
                    CONF_ENABLE_AP_SENSORS,
                    default=current_data.get(CONF_ENABLE_AP_SENSORS, DEFAULT_ENABLE_AP_SENSORS)
                ): bool,
                vol.Optional(
                    CONF_SYSTEM_SENSOR_TIMEOUT,
                    default=current_data.get(CONF_SYSTEM_SENSOR_TIMEOUT, DEFAULT_SYSTEM_SENSOR_TIMEOUT)
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                vol.Optional(
                    CONF_QMODEM_SENSOR_TIMEOUT,
                    default=current_data.get(CONF_QMODEM_SENSOR_TIMEOUT, DEFAULT_QMODEM_SENSOR_TIMEOUT)
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=600)),
                vol.Optional(
                    CONF_STA_SENSOR_TIMEOUT,
                    default=current_data.get(CONF_STA_SENSOR_TIMEOUT, DEFAULT_STA_SENSOR_TIMEOUT)
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                vol.Optional(
                    CONF_AP_SENSOR_TIMEOUT,
                    default=current_data.get(CONF_AP_SENSOR_TIMEOUT, DEFAULT_AP_SENSOR_TIMEOUT)
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=600)),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            description_placeholders={
                "host": self.config_entry.data[CONF_HOST]
            }
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
