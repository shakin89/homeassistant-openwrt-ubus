"""Constants for the openwrt_ubus integration."""

from homeassistant.const import Platform

DOMAIN = "openwrt_ubus"
PLATFORMS = [Platform.DEVICE_TRACKER, Platform.SENSOR]

# Configuration constants
CONF_DHCP_SOFTWARE = "dhcp_software"
CONF_WIRELESS_SOFTWARE = "wireless_software"
DEFAULT_DHCP_SOFTWARE = "dnsmasq"
DEFAULT_WIRELESS_SOFTWARE = "iwinfo"
DHCP_SOFTWARES = ["dnsmasq", "odhcpd", "none"]
WIRELESS_SOFTWARES = ["hostapd", "iwinfo"]

# API constants - moved from Ubus/const.py
API_RPC_CALL = "call"
API_RPC_LIST = "list"

# API parameters
API_PARAM_CONFIG = "config"
API_PARAM_PATH = "path"
API_PARAM_TYPE = "type"

# API subsystems
API_SUBSYS_DHCP = "dhcp"
API_SUBSYS_FILE = "file"
API_SUBSYS_HOSTAPD = "hostapd.*"
API_SUBSYS_IWINFO = "iwinfo"
API_SUBSYS_SYSTEM = "system"
API_SUBSYS_UCI = "uci"
API_SUBSYS_QMODEM = "modem_ctrl"

# API methods
API_METHOD_BOARD = "board"
API_METHOD_GET = "get"
API_METHOD_GET_AP = "devices"
API_METHOD_GET_CLIENTS = "get_clients"
API_METHOD_GET_STA = "assoclist"
API_METHOD_GET_QMODEM = "info"
API_METHOD_INFO = "info"
API_METHOD_READ = "read"
API_METHOD_REBOOT = "reboot"
