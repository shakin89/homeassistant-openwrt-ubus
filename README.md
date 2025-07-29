# OpenWrt Ubus Integration for Home Assistant

[中文版本](README_zh.md) | **English Version**

A custom Home Assistant integration that connects to OpenWrt routers via the ubus interface to provide device tracking and system monitoring capabilities.

## Features

### Device Tracking
- **Wireless Device Detection**: Track connected wireless devices using iwinfo or hostapd
- **DHCP Client Monitoring**: Monitor DHCP clients using dnsmasq or odhcpd
- **Real-time Connection Status**: Get live updates on device connectivity

### System Sensors
- **System Information**: Uptime, load averages, memory usage
- **QModem Support**: Monitor 4G/LTE modem status and connection details
- **Station Information**: Track wireless station associations and signal strength

### Advanced Features
- **Configurable Polling**: Adjustable update intervals for different sensor types
- **Multiple Software Support**: Compatible with various OpenWrt software configurations
- **Device Registry Integration**: Proper device identification and management

## Installation

### Method 1: Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/openwrt_ubus` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant
4. Go to **Configuration** → **Integrations** → **Add Integration**
5. Search for "OpenWrt ubus" and follow the setup wizard

### Method 2: HACS (Recommended)

*Note: This integration is not yet available in the default HACS repository*

1. Add this repository as a custom repository in HACS
2. Install the "OpenWrt ubus" integration
3. Restart Home Assistant
4. Add the integration through the UI

## Configuration

### Prerequisites

Your OpenWrt router must have:
- `rpcd` service running (usually enabled by default)
- `uhttpd` with ubus JSON-RPC support
- Valid user credentials with appropriate permissions

### Integration Setup

1. Navigate to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "OpenWrt ubus"
3. Enter your router configuration:
   - **Host**: IP address of your OpenWrt router
   - **Username**: Login username (usually 'root')
   - **Password**: Login password
   - **Wireless Software**: Choose between 'iwinfo' (default) or 'hostapd'
   - **DHCP Software**: Choose between 'dnsmasq' (default), 'odhcpd', or 'none'

### Configuration Options

| Option | Description | Default | Options |
|--------|-------------|---------|---------|
| Host | Router IP address | - | Any valid IP |
| Username | Login username | - | Usually 'root' |
| Password | Login password | - | Router password |
| Wireless Software | Wireless monitoring method | iwinfo | iwinfo, hostapd |
| DHCP Software | DHCP client detection method | dnsmasq | dnsmasq, odhcpd, none |

## Entities

### Device Tracker
- **Wireless Devices**: All connected wireless clients
- **DHCP Clients**: All DHCP-assigned devices (if DHCP monitoring enabled)

### Sensors

#### System Information
- `sensor.openwrt_uptime` - System uptime
- `sensor.openwrt_load_1` - 1-minute load average
- `sensor.openwrt_load_5` - 5-minute load average  
- `sensor.openwrt_load_15` - 15-minute load average
- `sensor.openwrt_memory_*` - Various memory statistics

#### QModem (4G/LTE Modem)
- `sensor.openwrt_qmodem_*` - Modem status, signal strength, connection details

#### Wireless Stations
- `sensor.openwrt_sta_*` - Station signal strength and connection information

## Troubleshooting

### Common Issues

**Cannot Connect to Router**
- Verify the router IP address and credentials
- Ensure `rpcd` and `uhttpd` services are running on OpenWrt
- Check firewall settings allow HTTP access to ubus

**No Devices Detected**
- Verify wireless and DHCP software settings match your OpenWrt configuration
- Check that the selected monitoring methods are properly configured on the router

**Sensors Not Updating**
- Check Home Assistant logs for connection errors
- Verify router permissions allow access to system information

### Debug Logging

Add to your `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.openwrt_ubus: debug
    homeassistant.components.device_tracker: debug
```

## OpenWrt Router Configuration

### Required Packages
Ensure these packages are installed on your OpenWrt router:

```bash
opkg install rpcd uhttpd-mod-ubus
```

### Service Configuration
Make sure required services are running:

```bash
service rpcd start
service rpcd enable
service uhttpd start  
service uhttpd enable
```

### Permissions
The user account needs appropriate permissions to access ubus methods. For the root user, this is typically not an issue.

## Development

### Project Structure
```
custom_components/openwrt_ubus/
├── __init__.py              # Main integration setup
├── config_flow.py           # Configuration flow
├── const.py                 # Constants and configuration
├── device_tracker.py        # Device tracking platform
├── sensor.py               # Sensor platform coordinator
├── manifest.json           # Integration manifest
├── strings.json            # UI strings
├── services.yaml           # Service definitions
├── Ubus/                   # Ubus communication library
│   ├── __init__.py
│   ├── const.py
│   └── interface.py
├── sensors/                # Individual sensor modules
│   ├── __init__.py
│   ├── system_sensor.py    # System information sensors
│   ├── qmodem_sensor.py    # QModem/LTE sensors
│   └── sta_sensor.py       # Wireless station sensors
└── translations/           # Localization files
    ├── en.json
    └── zh.json
```

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

- **GitHub Issues**: [Report bugs or request features](https://github.com/fujr/homeassistant-openwrt-ubus/issues)
- **Home Assistant Community**: [Discuss on the forum](https://community.home-assistant.io/)

## Acknowledgments

- OpenWrt project for the excellent router firmware
- Home Assistant community for integration development resources
- Contributors and testers who help improve this integration
