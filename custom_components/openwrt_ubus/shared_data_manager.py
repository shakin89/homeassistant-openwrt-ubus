"""Shared data manager for OpenWrt ubus API calls to reduce router load."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any, Dict, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .Ubus import Ubus, HostapdUbus, IwinfoUbus, QmodemUbus
from .const import CONF_DHCP_SOFTWARE, CONF_WIRELESS_SOFTWARE, DOMAIN, DEFAULT_DHCP_SOFTWARE, DEFAULT_WIRELESS_SOFTWARE

_LOGGER = logging.getLogger(__name__)


class SharedUbusDataManager:
    """Shared data manager for ubus API calls to reduce router load."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the shared data manager."""
        self.hass = hass
        self.entry = entry
        self._data_cache: Dict[str, Dict[str, Any]] = {}
        self._last_update: Dict[str, datetime] = {}
        self._update_intervals: Dict[str, timedelta] = {
            "system_info": timedelta(minutes=2),
            "system_board": timedelta(minutes=5),
            "qmodem_info": timedelta(minutes=1),
            "device_statistics": timedelta(seconds=30),
            "dhcp_leases": timedelta(seconds=30),
            "hostapd_clients": timedelta(seconds=30),
            "iwinfo_stations": timedelta(seconds=30),
        }
        self._update_locks: Dict[str, asyncio.Lock] = {
            key: asyncio.Lock() for key in self._update_intervals
        }
        
        # Initialize ubus clients
        self._ubus_clients: Dict[str, Ubus] = {}
        self._session = None
        
    async def _get_ubus_client(self, client_type: str = "default") -> Ubus:
        """Get or create ubus client instance."""
        if client_type not in self._ubus_clients:
            if self._session is None:
                self._session = async_get_clientsession(self.hass)
            
            url = f"http://{self.entry.data[CONF_HOST]}/ubus"
            username = self.entry.data[CONF_USERNAME]
            password = self.entry.data[CONF_PASSWORD]
            
            if client_type == "hostapd":
                client = HostapdUbus(url, username, password, session=self._session)
            elif client_type == "iwinfo":
                client = IwinfoUbus(url, username, password, session=self._session)
            elif client_type == "qmodem":
                client = QmodemUbus(url, username, password, session=self._session)
            else:
                client = Ubus(url, username, password, session=self._session)
            
            # Connect to the client
            try:
                session_id = await client.connect()
                if session_id is None:
                    raise UpdateFailed(f"Failed to connect to OpenWrt device")
                self._ubus_clients[client_type] = client
            except Exception as exc:
                _LOGGER.error("Failed to connect ubus client %s: %s", client_type, exc)
                raise UpdateFailed(f"Failed to connect ubus client {client_type}: {exc}")
                
        return self._ubus_clients[client_type]

    async def _should_update(self, data_type: str) -> bool:
        """Check if data should be updated based on interval."""
        if data_type not in self._last_update:
            return True
        
        interval = self._update_intervals.get(data_type, timedelta(minutes=1))
        return datetime.now() - self._last_update[data_type] > interval

    async def _fetch_system_info(self) -> Dict[str, Any]:
        """Fetch system information."""
        client = await self._get_ubus_client()
        try:
            system_info = await client.system_info()
            return {"system_info": system_info}
        except Exception as exc:
            _LOGGER.error("Error fetching system info: %s", exc)
            raise UpdateFailed(f"Error fetching system info: {exc}")

    async def _fetch_system_board(self) -> Dict[str, Any]:
        """Fetch system board information."""
        client = await self._get_ubus_client()
        try:
            board_info = await client.system_board()
            return {"system_board": board_info}
        except Exception as exc:
            _LOGGER.error("Error fetching system board: %s", exc)
            raise UpdateFailed(f"Error fetching system board: {exc}")

    async def _fetch_qmodem_info(self) -> Dict[str, Any]:
        """Fetch QModem information if available."""
        if not self.hass.data[DOMAIN].get("modem_ctrl_available", False):
            return {"qmodem_info": None}
            
        client = await self._get_ubus_client("qmodem")
        try:
            qmodem_info = await client.get_qmodem_info()
            _LOGGER.debug("QModem data fetched successfully")
            return {"qmodem_info": qmodem_info}
        except Exception as exc:
            _LOGGER.debug("Error fetching QModem info: %s", exc)
            return {"qmodem_info": None}

    async def _fetch_device_statistics(self) -> Dict[str, Any]:
        """Fetch device statistics from wireless interfaces."""
        wireless_software = self.entry.data.get(CONF_WIRELESS_SOFTWARE, "iwinfo")
        dhcp_software = self.entry.data.get(CONF_DHCP_SOFTWARE, "dnsmasq")
        
        try:
            # Get MAC to name/IP mapping first
            mac2name = await self._get_mac2name_mapping(dhcp_software)
            
            # Get device statistics and connection info
            if wireless_software == "hostapd":
                return await self._fetch_hostapd_data(mac2name)
            else:
                return await self._fetch_iwinfo_data(mac2name)
        except Exception as exc:
            _LOGGER.error("Error fetching device statistics: %s", exc)
            raise UpdateFailed(f"Error fetching device statistics: {exc}")

    async def _fetch_hostapd_data(self, mac2name: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
        """Fetch data from hostapd."""
        client = await self._get_ubus_client("hostapd")
        try:
            # Get AP devices
            ap_devices_result = await client.get_ap_devices()
            ap_devices = client.parse_ap_devices(ap_devices_result) if ap_devices_result else []
            
            device_statistics = {}
            for ap_device in ap_devices:
                try:
                    # Get station devices for tracking
                    sta_devices_result = await client.get_sta_devices(ap_device)
                    sta_devices = client.parse_sta_devices(sta_devices_result) if sta_devices_result else []
                    
                    # Get detailed statistics for sensors
                    sta_stats_result = await client.get_sta_statistics(ap_device)
                    sta_stats = client.parse_sta_statistics(sta_stats_result) if sta_stats_result else {}
                    
                    for mac in sta_devices:
                        normalized_mac = mac.upper()
                        hostname = mac2name.get(normalized_mac, {}).get("hostname", normalized_mac.replace(":", ""))
                        ip_address = mac2name.get(normalized_mac, {}).get("ip", "Unknown IP")
                        
                        # Merge connection info with detailed statistics
                        device_info = {
                            "mac": normalized_mac,
                            "hostname": hostname,
                            "ap_device": ap_device,
                            "connected": True,
                            "ip_address": ip_address,
                        }
                        
                        # Add statistics if available
                        if normalized_mac in sta_stats:
                            device_info.update(sta_stats[normalized_mac])
                        
                        device_statistics[normalized_mac] = device_info
                        
                except Exception as exc:
                    _LOGGER.debug("Error fetching hostapd data for %s: %s", ap_device, exc)
            
            return {"device_statistics": device_statistics}
        except Exception as exc:
            _LOGGER.error("Error fetching hostapd data: %s", exc)
            raise UpdateFailed(f"Error fetching hostapd data: {exc}")

    async def _fetch_iwinfo_data(self, mac2name: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
        """Fetch data from iwinfo."""
        client = await self._get_ubus_client("iwinfo")
        try:
            # Get AP devices
            ap_devices_result = await client.get_ap_devices()
            ap_devices = client.parse_ap_devices(ap_devices_result) if ap_devices_result else []
            
            device_statistics = {}
            for ap_device in ap_devices:
                try:
                    # Get station devices for tracking
                    sta_devices_result = await client.get_sta_devices(ap_device)
                    sta_devices = client.parse_sta_devices(sta_devices_result) if sta_devices_result else []
                    
                    # Get detailed statistics for sensors
                    sta_stats_result = await client.get_sta_statistics(ap_device)
                    sta_stats = client.parse_sta_statistics(sta_stats_result) if sta_stats_result else {}
                    
                    for mac in sta_devices:
                        normalized_mac = mac.upper()
                        hostname = mac2name.get(normalized_mac, {}).get("hostname", normalized_mac.replace(":", ""))
                        ip_address = mac2name.get(normalized_mac, {}).get("ip", "Unknown IP")
                        
                        # Merge connection info with detailed statistics
                        device_info = {
                            "mac": normalized_mac,
                            "hostname": hostname,
                            "ap_device": ap_device,
                            "connected": True,
                            "ip_address": ip_address,
                        }
                        
                        # Add statistics if available
                        if normalized_mac in sta_stats:
                            device_info.update(sta_stats[normalized_mac])
                        
                        device_statistics[normalized_mac] = device_info
                        
                except Exception as exc:
                    _LOGGER.debug("Error fetching iwinfo data for %s: %s", ap_device, exc)
            
            return {"device_statistics": device_statistics}
        except Exception as exc:
            _LOGGER.error("Error fetching iwinfo data: %s", exc)
            raise UpdateFailed(f"Error fetching iwinfo data: {exc}")

    async def _get_mac2name_mapping(self, dhcp_software: str) -> Dict[str, Dict[str, str]]:
        """Generate MAC to name/IP mapping based on DHCP server."""
        mac2name = {}
        client = await self._get_ubus_client()
        
        try:
            if dhcp_software == "dnsmasq":
                # Get dnsmasq lease file location
                result = await client.get_uci_config("dhcp", "dnsmasq")
                if result and "values" in result:
                    values = result["values"].values()
                    leasefile = next(iter(values), {}).get("leasefile", "/tmp/dhcp.leases")
                    
                    # Read lease file
                    lease_result = await client.file_read(leasefile)
                    if lease_result and "data" in lease_result:
                        for line in lease_result["data"].splitlines():
                            hosts = line.split(" ")
                            if len(hosts) >= 4:
                                mac2name[hosts[1].upper()] = {
                                    "hostname": hosts[3],
                                    "ip": hosts[2]
                                }
            elif dhcp_software == "odhcpd":
                # Get odhcpd leases
                result = await client.get_dhcp_method("ipv4leases")
                if result and "device" in result:
                    for device in result["device"].values():
                        for lease in device.get("leases", []):
                            mac = lease.get("mac", "")
                            # Convert aabbccddeeff to aa:bb:cc:dd:ee:ff
                            if mac and len(mac) == 12:
                                mac = ":".join(mac[i:i+2] for i in range(0, len(mac), 2))
                                mac2name[mac.upper()] = {
                                    "hostname": lease.get("hostname", ""),
                                    "ip": lease.get("ip", "")
                                }
        except Exception as exc:
            _LOGGER.warning("Failed to get MAC to name mapping: %s", exc)
        
        return mac2name

    async def get_data(self, data_type: str) -> Dict[str, Any]:
        """Get cached data or fetch if needed."""
        async with self._update_locks[data_type]:
            if not await self._should_update(data_type) and data_type in self._data_cache:
                return self._data_cache[data_type]

            try:
                if data_type == "system_info":
                    data = await self._fetch_system_info()
                elif data_type == "system_board":
                    data = await self._fetch_system_board()
                elif data_type == "qmodem_info":
                    data = await self._fetch_qmodem_info()
                elif data_type == "device_statistics":
                    data = await self._fetch_device_statistics()
                else:
                    raise ValueError(f"Unknown data type: {data_type}")

                self._data_cache[data_type] = data
                self._last_update[data_type] = datetime.now()
                return data
            except Exception as exc:
                _LOGGER.error("Error fetching data for %s: %s", data_type, exc)
                # Return cached data if available
                if data_type in self._data_cache:
                    _LOGGER.debug("Returning cached data for %s", data_type)
                    return self._data_cache[data_type]
                raise

    async def get_combined_data(self, data_types: list[str]) -> Dict[str, Any]:
        """Get multiple data types in a single call to optimize API usage."""
        combined_data = {}
        
        # Group data types that can be fetched together
        system_types = {"system_info", "system_board"} & set(data_types)
        other_types = set(data_types) - system_types
        
        # Fetch system data together if needed
        if system_types:
            system_client = await self._get_ubus_client()
            try:
                if "system_info" in system_types:
                    if await self._should_update("system_info"):
                        async with self._update_locks["system_info"]:
                            system_info = await system_client.system_info()
                            self._data_cache["system_info"] = {"system_info": system_info}
                            self._last_update["system_info"] = datetime.now()
                    combined_data.update(self._data_cache["system_info"])
                
                if "system_board" in system_types:
                    if await self._should_update("system_board"):
                        async with self._update_locks["system_board"]:
                            board_info = await system_client.system_board()
                            self._data_cache["system_board"] = {"system_board": board_info}
                            self._last_update["system_board"] = datetime.now()
                    combined_data.update(self._data_cache["system_board"])
            except Exception as exc:
                _LOGGER.error("Error fetching system data: %s", exc)
                # Use cached data if available
                for data_type in system_types:
                    if data_type in self._data_cache:
                        combined_data.update(self._data_cache[data_type])
        
        # Fetch other data types individually
        for data_type in other_types:
            try:
                data = await self.get_data(data_type)
                combined_data.update(data)
            except Exception as exc:
                _LOGGER.error("Error fetching %s: %s", data_type, exc)
        
        return combined_data

    async def close(self):
        """Close all ubus client connections."""
        for client in self._ubus_clients.values():
            try:
                await client.close()
            except Exception as exc:
                _LOGGER.debug("Error closing ubus client: %s", exc)
        self._ubus_clients.clear()

    def set_update_interval(self, data_type: str, interval: timedelta):
        """Set custom update interval for a data type."""
        self._update_intervals[data_type] = interval
        if data_type not in self._update_locks:
            self._update_locks[data_type] = asyncio.Lock()

    def invalidate_cache(self, data_type: str = None):
        """Invalidate cache for specific data type or all data."""
        if data_type:
            self._data_cache.pop(data_type, None)
            self._last_update.pop(data_type, None)
        else:
            self._data_cache.clear()
            self._last_update.clear()


class SharedDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator that uses shared data manager."""

    def __init__(
        self,
        hass: HomeAssistant,
        data_manager: SharedUbusDataManager,
        data_types: list[str],
        name: str,
        update_interval: timedelta,
    ):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=update_interval,
        )
        self.data_manager = data_manager
        self.data_types = data_types

    async def _async_update_data(self):
        """Fetch data using shared manager."""
        try:
            return await self.data_manager.get_combined_data(self.data_types)
        except Exception as exc:
            raise UpdateFailed(f"Error communicating with API: {exc}")

    async def async_shutdown(self):
        """Shutdown the coordinator."""
        # Note: Don't close the data manager here as it might be shared
        # The data manager will be closed when the integration is unloaded
        pass
