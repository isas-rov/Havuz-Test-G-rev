#!/usr/bin/env bash
set -euo pipefail

# Make the saved pool/phone hotspot profile reconnect indefinitely after the
# vehicle surfaces. Modifying a profile does not intentionally disconnect the
# currently active session; the values are used on the next activation.
profile="${1:-ISAS-Phone}"

if ! nmcli -g connection.id connection show "$profile" >/dev/null 2>&1; then
    echo "NetworkManager profile not found: $profile" >&2
    echo "Available profiles:" >&2
    nmcli -f NAME,TYPE,DEVICE connection show >&2
    exit 1
fi

nmcli connection modify "$profile" \
    connection.autoconnect yes \
    connection.autoconnect-priority 50 \
    connection.autoconnect-retries 0 \
    802-11-wireless.powersave 2

echo "Pool Wi-Fi reconnect policy configured for: $profile"
nmcli -f \
connection.id,connection.autoconnect,connection.autoconnect-priority,connection.autoconnect-retries,802-11-wireless.ssid,802-11-wireless.powersave \
connection show "$profile"
