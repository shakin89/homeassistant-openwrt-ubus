"""Client for the OpenWrt ubus API."""

import json
import logging

import aiohttp

from .const import (
    API_DEF_DEBUG,
    API_DEF_SESSION_ID,
    API_DEF_TIMEOUT,
    API_DEF_VERIFY,
    API_ERROR,
    API_MESSAGE,
    API_METHOD_BOARD,
    API_METHOD_GET,
    API_METHOD_GET_AP,
    API_METHOD_GET_CLIENTS,
    API_METHOD_GET_STA,
    API_METHOD_INFO,
    API_METHOD_LOGIN,
    API_METHOD_READ,
    API_METHOD_REBOOT,
    API_PARAM_CONFIG,
    API_PARAM_PASSWORD,
    API_PARAM_PATH,
    API_PARAM_TYPE,
    API_PARAM_USERNAME,
    API_RESULT,
    API_RPC_CALL,
    API_RPC_ID,
    API_RPC_LIST,
    API_RPC_VERSION,
    API_SUBSYS_DHCP,
    API_SUBSYS_FILE,
    API_SUBSYS_HOSTAPD,
    API_SUBSYS_IWINFO,
    API_SUBSYS_SESSION,
    API_SUBSYS_SYSTEM,
    API_SUBSYS_UCI,
    API_UBUS_RPC_SESSION,
    API_SUBSYS_QMODEM,
    API_METHOD_GET_QMODEM,
    HTTP_STATUS_OK,
)

_LOGGER = logging.getLogger(__name__)


class Ubus:
    """Interacts with the OpenWrt ubus API."""

    def __init__(
        self,
        host,
        username,
        password,
        session=None,
        timeout=API_DEF_TIMEOUT,
        verify=API_DEF_VERIFY,
    ):
        """Init OpenWrt ubus API."""
        self.host = host
        self.username = username
        self.password = password
        self.session = session  # Session will be provided externally
        self.timeout = timeout
        self.verify = verify

        self.debug_api = API_DEF_DEBUG
        self.rpc_id = API_RPC_ID
        self.session_id = None
        self._session_created_internally = False

    def set_session(self, session):
        """Set the aiohttp session to use."""
        self.session = session

    def _ensure_session(self):
        """Ensure we have a session, create one if needed."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
            self._session_created_internally = True

    async def call_apis(self, apis: list):
        self._ensure_session()

    async def api_call(
        self,
        rpc_method,
        subsystem=None,
        method=None,
        params: dict | None = None,
    ):
        """Perform API call."""
        # Ensure we have a session
        self._ensure_session()

        if self.debug_api:
            _LOGGER.debug(
                'api call: rpc_method="%s" subsystem="%s" method="%s" params="%s"',
                rpc_method,
                subsystem,
                method,
                params,
            )

        _params = [self.session_id, subsystem]
        if rpc_method == API_RPC_CALL:
            if method:
                _params.append(method)

            if params:
                _params.append(params)
            else:
                _params.append({})

        data = json.dumps(
            {
                "jsonrpc": API_RPC_VERSION,
                "id": self.rpc_id,
                "method": rpc_method,
                "params": _params,
            }
        )
        if self.debug_api:
            _LOGGER.debug('api call: data="%s"', data)

        self.rpc_id += 1
        try:
            response = await self.session.post(
                self.host, data=data, timeout=self.timeout, verify_ssl=self.verify
            )
        except aiohttp.ClientError as req_exc:
            _LOGGER.error("api_call exception: %s", req_exc)
            return None

        if response.status != HTTP_STATUS_OK:
            return None

        json_response = await response.json()

        if self.debug_api:
            _LOGGER.debug(
                'api call: status="%s" response="%s"',
                response.status,
                response.text,
            )

        if API_ERROR in json_response:
            if (
                API_MESSAGE in json_response[API_ERROR]
                and json_response[API_ERROR][API_MESSAGE] == "Access denied"
            ):
                raise PermissionError(json_response[API_ERROR][API_MESSAGE])
            raise ConnectionError(json_response[API_ERROR][API_MESSAGE])

        if rpc_method == API_RPC_CALL:
            try:
                return json_response[API_RESULT][1]
            except IndexError:
                return None
        else:
            return json_response[API_RESULT]

    def api_debugging(self, debug_api):
        """Enable/Disable API calls debugging."""
        self.debug_api = debug_api
        return self.debug_api

    def https_verify(self, verify):
        """Enable/Disable HTTPS verification."""
        self.verify = verify
        return self.verify

    async def connect(self):
        """Connect to OpenWrt ubus API."""
        self.rpc_id = 1
        self.session_id = API_DEF_SESSION_ID

        login = await self.api_call(
            API_RPC_CALL,
            API_SUBSYS_SESSION,
            API_METHOD_LOGIN,
            {
                API_PARAM_USERNAME: self.username,
                API_PARAM_PASSWORD: self.password,
            },
        )
        if API_UBUS_RPC_SESSION in login:
            self.session_id = login[API_UBUS_RPC_SESSION]
        else:
            self.session_id = None

        return self.session_id

    async def file_read(self, path):
        """Get UCI config."""
        return await self.api_call(
            API_RPC_CALL,
            API_SUBSYS_FILE,
            API_METHOD_READ,
            {
                API_PARAM_PATH: path,
            },
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

    async def close(self):
        """Close the aiohttp session if we created it internally."""
        if self.session and not self.session.closed and self._session_created_internally:
            await self.session.close()
            self.session = None
            self._session_created_internally = False

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

class IwinfoUbus(Ubus):
    """Client for iwinfo-based device discovery."""

    def __init__(
        self,
        host,
        username,
        password,
        session=None,
        timeout=API_DEF_TIMEOUT,
        verify=API_DEF_VERIFY,
    ):
        """Initialize the iwinfo client."""
        super().__init__(host, username, password, session, timeout, verify)

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
            device["mac"] for device in result.get("results", {})
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

class HostapdUbus(Ubus):
    """Client for hostapd-based device discovery."""

    def __init__(
        self,
        host,
        username,
        password,
        session=None,
        timeout=API_DEF_TIMEOUT,
        verify=API_DEF_VERIFY,
    ):
        """Initialize the hostapd client."""
        super().__init__(host, username, password, session, timeout, verify)

    async def get_ap_devices(self):
        """Get access point devices from hostapd."""
        return await self.get_hostapd()

    async def get_sta_devices(self, hostapd):
        """Get station devices from hostapd."""
        return await self.get_hostapd_clients(hostapd)

    def parse_sta_devices(self, result):
        """Parse station devices from the ubus result."""
        sta_devices = []
        if not result:
            return sta_devices

        for key in result.get("clients", {}):
                device = result["clients"][key]
                if device.get("authorized"):
                    sta_devices.append(key)
        return sta_devices

    def parse_ap_devices(self, result):
        """Parse access point devices from the ubus result."""
        return result

class QmodemUbus(Ubus):
    """QModem Info Retriever."""
    def __init__(
        self,
        host,
        username,
        password,
        session=None,
        timeout=API_DEF_TIMEOUT,
        verify=API_DEF_VERIFY,
    ):
        """Initialize the QModem client."""
        super().__init__(host, username, password, session, timeout, verify)
