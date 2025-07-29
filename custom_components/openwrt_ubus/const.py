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

# API constants
API_SUBSYS_IWINFO = "iwinfo"
API_METHOD_GET_AP = "devices"
API_METHOD_GET_STA = "assoclist"
API_RPC_CALL = "call"
