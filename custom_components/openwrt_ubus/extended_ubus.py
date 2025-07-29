"""Extended Ubus client with specific OpenWrt functionality."""

import json
import logging

from .Ubus import Ubus
from .const import (
    API_RPC_CALL,
    API_RPC_LIST,
    API_PARAM_CONFIG,
    API_PARAM_PATH,
    API_PARAM_TYPE,
    API_SUBSYS_DHCP,
    API_SUBSYS_FILE,
    API_SUBSYS_HOSTAPD,
    API_SUBSYS_IWINFO,
    API_SUBSYS_SYSTEM,
    API_SUBSYS_UCI,
    API_SUBSYS_QMODEM,
    API_METHOD_BOARD,
    API_METHOD_GET,
    API_METHOD_GET_AP,
    API_METHOD_GET_CLIENTS,
    API_METHOD_GET_STA,
    API_METHOD_GET_QMODEM,
    API_METHOD_INFO,
    API_METHOD_READ,
    API_METHOD_REBOOT,
)

_LOGGER = logging.getLogger(__name__)


class ExtendedUbus(Ubus):
    """Extended Ubus client with specific OpenWrt functionality."""

    async def file_read(self, path):
        """Read file content."""
        return await self.api_call(
            API_RPC_CALL,
            API_SUBSYS_FILE,
            API_METHOD_READ,
            {API_PARAM_PATH: path},
        )

    async def get_dhcp_method(self, method):
        """Get DHCP method."""
        return await self.api_call(API_RPC_CALL, API_SUBSYS_DHCP, method)

    async def get_hostapd(self):
        """Get hostapd data."""
        return await self.api_call(API_RPC_LIST, API_SUBSYS_HOSTAPD)

    async def get_hostapd_clients(self, hostapd):
        """Get hostapd clients."""
        return await self.api_call(API_RPC_CALL, hostapd, API_METHOD_GET_CLIENTS)

    async def get_uci_config(self, _config, _type):
        """Get UCI config."""
        return await self.api_call(
            API_RPC_CALL,
            API_SUBSYS_UCI,
            API_METHOD_GET,
            {
                API_PARAM_CONFIG: _config,
                API_PARAM_TYPE: _type,
            },
        )

    async def list_modem_ctrl(self):
        """List available modem_ctrl subsystems."""
        return await self.api_call(API_RPC_LIST, API_SUBSYS_QMODEM)

    async def get_qmodem_info(self):
        """Get QModem info."""
        return await self.api_call(API_RPC_CALL, API_SUBSYS_QMODEM, API_METHOD_GET_QMODEM)

    async def get_system_method(self, method):
        """Get system method."""
        return await self.api_call(API_RPC_CALL, API_SUBSYS_SYSTEM, method)

    async def system_board(self):
        """System board."""
        return await self.get_system_method(API_METHOD_BOARD)

    async def system_info(self):
        """System info."""
        return await self.get_system_method(API_METHOD_INFO)

    async def system_reboot(self):
        """System reboot."""
        return await self.get_system_method(API_METHOD_REBOOT)

    # iwinfo specific methods
    async def get_ap_devices(self):
        """Get access point devices."""
        return await self.api_call(API_RPC_CALL, API_SUBSYS_IWINFO, API_METHOD_GET_AP)

    async def get_sta_devices(self, ap_device):
        """Get station devices."""
        return await self.api_call(API_RPC_CALL, API_SUBSYS_IWINFO, API_METHOD_GET_STA, {"device": ap_device})

    async def get_sta_statistics(self, ap_device):
        """Get detailed station statistics for all connected devices."""
        return await self.api_call(API_RPC_CALL, API_SUBSYS_IWINFO, API_METHOD_GET_STA, {"device": ap_device})

    def parse_sta_devices(self, result):
        """Parse station devices from the ubus result."""
        sta_devices = []
        if not result:
            return sta_devices

        # iwinfo format
        sta_devices.extend(
            device["mac"] for device in result.get("results", [])
        )
        return sta_devices

    def parse_sta_statistics(self, result):
        """Parse detailed station statistics from the ubus result."""
        sta_statistics = {}
        if not result:
            return sta_statistics

        # iwinfo format - each device has detailed statistics
        for device in result.get("results", []):
            if "mac" in device:
                sta_statistics[device["mac"]] = device
        return sta_statistics

    def parse_ap_devices(self, result):
        """Parse access point devices from the ubus result."""
        return list(result.get("devices", []))

    # hostapd specific methods
    def parse_hostapd_sta_devices(self, result):
        """Parse station devices from hostapd ubus result."""
        sta_devices = []
        if not result:
            return sta_devices

        for key in result.get("clients", {}):
            device = result["clients"][key]
            if device.get("authorized"):
                sta_devices.append(key)
        return sta_devices

    def parse_hostapd_sta_statistics(self, result):
        """Parse detailed station statistics from hostapd ubus result."""
        sta_statistics = {}
        if not result:
            return sta_statistics

        # hostapd format - each device has detailed statistics
        for mac, device in result.get("clients", {}).items():
            if device.get("authorized"):
                sta_statistics[mac] = device
        return sta_statistics

    def parse_hostapd_ap_devices(self, result):
        """Parse access point devices from hostapd ubus result."""
        return result

    async def get_all_sta_data_batch(self, ap_devices, is_hostapd=False):
        """Get station data for all AP devices using batch call."""
        if not ap_devices:
            return {}
        
        # Build API calls for all AP devices
        rpcs = []
        for i, ap_device in enumerate(ap_devices):
            if is_hostapd:
                # For hostapd, ap_device is the hostapd interface name
                api_call = json.loads(self.build_api(
                    API_RPC_CALL,
                    ap_device,
                    API_METHOD_GET_CLIENTS
                ))
            else:
                # For iwinfo, ap_device is the wireless interface name
                api_call = json.loads(self.build_api(
                    API_RPC_CALL,
                    API_SUBSYS_IWINFO,
                    API_METHOD_GET_STA,
                    {"device": ap_device}
                ))
            api_call["id"] = i  # Use index as ID to match responses
            rpcs.append(api_call)
        
        # Execute batch call
        results = await self.batch_call(rpcs)
        if not results:
            return {}
        
        # Process results
        sta_data = {}
        for i, result in enumerate(results):
            if i < len(ap_devices):
                ap_device = ap_devices[i]
                try:
                    # Handle different response formats
                    if "result" in result:
                        sta_result = result["result"][1] if len(result["result"]) > 1 else None
                    elif "error" in result:
                        _LOGGER.debug("Error in batch call for %s: %s", ap_device, result["error"])
                        continue
                    else:
                        continue
                        
                    if sta_result:
                        if is_hostapd:
                            sta_data[ap_device] = {
                                'devices': self.parse_hostapd_sta_devices(sta_result),
                                'statistics': self.parse_hostapd_sta_statistics(sta_result)
                            }
                        else:
                            sta_data[ap_device] = {
                                'devices': self.parse_sta_devices(sta_result),
                                'statistics': self.parse_sta_statistics(sta_result)
                            }
                except (IndexError, KeyError) as exc:
                    _LOGGER.debug("Error parsing sta data for %s: %s", ap_device, exc)
                    
        return sta_data
