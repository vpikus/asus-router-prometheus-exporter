"""
Test fixtures based on real ASUS Router API responses.
"""

# Memory usage response
MEMORY_USAGE_RESPONSE = """{
"memory_usage":"mem_total":"1048576","mem_free":"549036","mem_used":"499540"
}
"""

# CPU usage response
CPU_USAGE_RESPONSE = """{
"cpu_usage":"cpu1_total":"3367570","cpu1_usage":"141252","cpu2_total":"3377595","cpu2_usage":"72288","cpu3_total":"3379481","cpu3_usage":"67899","cpu4_total":"3378600","cpu4_usage":"65971"
}
"""

# Netdev response
NETDEV_RESPONSE = """{
"netdev":{ "BRIDGE_rx":"0x78023dfa","BRIDGE_tx":"0x1e2a5ad36","INTERNET1_rx":"0x2411e3","INTERNET1_tx":"0x263542","INTERNET_rx":"0x1953f3b1c","INTERNET_tx":"0x64d91bfe","WIRED_rx":"0x1efd44512","WIRED_tx":"0x65419187","WIRELESS0_rx":"0x3466739","WIRELESS0_tx":"0x36b33891","WIRELESS1_rx":"0x5abeaf13","WIRELESS1_tx":"0x2cb2aced2"}
}
"""

# Uptime response
UPTIME_RESPONSE = """{
"uptime":"Thu, 01 Jan 2026 13:26:53 +0200(33962 secs since boot)"
}
"""

# Temperature response (from ajax_coretmp.asp)
CORE_TEMP_RESPONSE = """fanctrl_info = ;
curr_cpuTemp = "52.759";
curr_rxData = fanctrl_info[3];
curr_coreTmp_2 = fanctrl_info[1];
curr_coreTmp_5 = fanctrl_info[2];
"""

# WL nband info response
WL_NBAND_INFO_RESPONSE = """{
"wl_nband_info":["2", "1"]
}
"""

# Get WAN unit response
GET_WAN_UNIT_RESPONSE = """{
"get_wan_unit":0
}
"""

# SW mode NVRAM response
SW_MODE_NVRAM_RESPONSE = """{
"sw_mode":"1",
"wlc_psta":"0",
"wlc_express":"0"
}
"""

# Dual WAN NVRAM response
DUAL_WAN_NVRAM_RESPONSE = """{
"wans_dualwan":"wan lan",
"wan0_enable":"1",
"wan1_enable":"1",
"wans_mode":"lb"
}
"""

# WAN state NVRAM response
WAN_STATE_NVRAM_RESPONSE = """{
"wan0_state_t":"2",
"wan0_sbstate_t":"0",
"wan0_auxstate_t":"0",
"link_internet":"2"
}
"""

# WAN IP/proto NVRAM response
WAN_IP_PROTO_NVRAM_RESPONSE = """{
"wan0_ipaddr":"94.100.50.25",
"wan0_proto":"dhcp"
}
"""

# Link internet NVRAM response
LINK_INTERNET_NVRAM_RESPONSE = """{
"link_internet":"2"
}
"""

# WPS/WLC NVRAM response
WPS_WLC_NVRAM_RESPONSE = """{
"wps_enable":"0",
"wlc_band":"",
"smart_connect_x":"0"
}
"""

# Wireless band info NVRAM response
WL0_BAND_NVRAM_RESPONSE = """{
"wl0_mbo_enable":"0",
"wl0_ssid":"MyNetwork",
"wl0_nmode_x":"0",
"wl0_auth_mode_x":"psk2",
"wl0_crypto":"aes",
"wl0_mfp":"0",
"wl0_wep_x":"0",
"wl0_closed":"0",
"wl0_hwaddr":"04:42:1A:0F:9E:D0"
}
"""

WL1_BAND_NVRAM_RESPONSE = """{
"wl1_mbo_enable":"0",
"wl1_ssid":"MyNetwork_5G",
"wl1_nmode_x":"0",
"wl1_auth_mode_x":"psk2",
"wl1_crypto":"aes",
"wl1_mfp":"0",
"wl1_wep_x":"0",
"wl1_closed":"0",
"wl1_hwaddr":"04:42:1A:0F:9E:D1"
}
"""

# Reboot schedule NVRAM response
REBOOT_SCHEDULE_NVRAM_RESPONSE = """{
"reboot_schedule_enable":"1",
"reboot_schedule":"10001000400"
}
"""

# Port status response
PORT_STATUS_RESPONSE = """{ "node_info": { "04:42:1A:0F:9E:D0": { "cd_good_to_go": "1" } }, "port_info": { "04:42:1A:0F:9E:D0": { "W0": { "is_on": "1", "cap": "1073741825", "max_rate": "1000", "link_rate": "1000" }, "L1": { "is_on": "1", "cap": "536870914", "max_rate": "1000", "link_rate": "100" }, "L2": { "is_on": "1", "cap": "2", "max_rate": "1000", "link_rate": "1000" }, "L3": { "is_on": "1", "cap": "2", "max_rate": "1000", "link_rate": "100" }, "L4": { "is_on": "0", "cap": "2", "max_rate": "1000", "link_rate": "0" } } } }"""

# UI Support response
UI_SUPPORT_RESPONSE = """{
"get_ui_support":{ "mssid": 1, "2.4G": 1, "5G": 1, "dualwan": 1, "reboot_schedule": 1, "stainfo": 1, "amas": 2, "force_roaming": 1, "sta_ap_bind": 1, "usbX": 1 }
}
"""

# Router info NVRAM response
ROUTER_INFO_NVRAM_RESPONSE = """{
"productid":"RT-AX88U",
"lan_hwaddr":"04:42:1A:0F:9E:D0",
"lan_hostname":"RT-AX88U-Router",
"odmpid":"",
"hardware_version":"1.0",
"bl_version":"3.0.0.4",
"svc_ready":"1",
"qos_enable":"0",
"bwdpi_app_rulelist":"",
"qos_type":"0",
"firmver":"3.0.0.4",
"extendno":"388.4",
"territory_code":"EU",
"re_mode":"0",
"serial_no":"ABC123456789",
"webs_state_flag":"0"
}
"""

# Get clientlist response
GET_CLIENTLIST_RESPONSE = """{
"get_clientlist":{ "04:42:1A:0F:9E:D0": { "type": "", "defaultType": "0", "name": "RT-AX88U", "nickName": "", "ip": "192.168.1.1", "mac": "04:42:1A:0F:9E:D0", "from": "networkmapd", "macRepeat": "1", "isGateway": "1", "isWebServer": "0", "isPrinter": "0", "isITunes": "0", "isASUS": "0", "opMode": "0", "rssi": "", "curTx": "", "curRx": "", "totalTx": "", "totalRx": "", "wlConnectTime": "", "ipMethod": "", "ROG": "0", "group": "", "callback": "", "keeparp": "", "qosLevel": "", "amesh_isReClient": "", "amesh_papMac": "", "isWL": "0", "isOnline": "1", "ssid": "", "isLogin": "1", "internetMode": "allow", "internetState": "1", "vendor": "ASUS" }, "AA:BB:CC:DD:EE:FF": { "name": "TestDevice", "nickName": "My Phone", "ip": "192.168.1.100", "mac": "AA:BB:CC:DD:EE:FF", "opMode": "0", "rssi": "-55", "curTx": "1024", "curRx": "2048", "totalTx": "1000000", "totalRx": "2000000", "wlConnectTime": "01:30:45", "ipMethod": "DHCP", "isWL": "1", "isOnline": "1", "internetMode": "allow", "internetState": "1", "vendor": "Apple" } }
}
"""

# Get clientlist from database response
GET_CLIENTLIST_DB_RESPONSE = """{
"get_clientlist_from_json_database":{ "04:42:1A:0F:9E:D0": { "mac": "04:42:1A:0F:9E:D0", "name": "RT-AX88U", "nickName": "", "vendor": "ASUS", "type": "0", "os_type": "0", "online": "1", "conn_ts": "1735730000", "is_wireless": "0", "amesh_isRe": "0", "amesh_bind_band": "", "amesh_bind_mac": "" }, "AA:BB:CC:DD:EE:FF": { "mac": "AA:BB:CC:DD:EE:FF", "name": "TestDevice", "nickName": "My Phone", "vendor": "Apple", "type": "10", "os_type": "5", "online": "1", "conn_ts": "1735730100", "is_wireless": "1", "amesh_isRe": "0", "amesh_bind_band": "", "amesh_bind_mac": "" } }
}
"""

# Show USB path response
SHOW_USB_PATH_RESPONSE = """{
"show_usb_path":["storage", "modem"]
}
"""

# Login response (successful)
LOGIN_SUCCESS_RESPONSE = """{"asus_token": "abc123def456"}"""

# Login response (error)
LOGIN_ERROR_RESPONSE = """{"error_status": "2"}"""
