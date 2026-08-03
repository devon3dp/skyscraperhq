#!/bin/bash
# 2026-07-23: the whole tower calls the brain/HQ at 192.168.1.72. The M1's DHCP kept moving Wren's box
# off .72 (to .71), breaking every CEO's brain access ("brain unavailable"). Pin .72 as a stable
# secondary on the WiFi iface so it always answers there regardless of the DHCP lease.
IFACE=wlp12s0
ip -4 addr show "$IFACE" 2>/dev/null | grep -q '192.168.1.72/' || ip addr add 192.168.1.72/24 dev "$IFACE" 2>/dev/null
