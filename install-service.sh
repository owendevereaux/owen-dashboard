#!/bin/bash
# Install Owen Dashboard as a launchd service (macOS)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.owen.dashboard"
PLIST_PATH="/Library/LaunchDaemons/${PLIST_NAME}.plist"
LOG_DIR="/Users/Shared/owen/workspace/logs"

echo "Installing Owen Dashboard service..."

# Create log directory
mkdir -p "$LOG_DIR"

# Create plist
cat > /tmp/${PLIST_NAME}.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>${SCRIPT_DIR}/server.py</string>
        <string>--port</string>
        <string>8766</string>
        <string>--workspace</string>
        <string>/Users/Shared/owen/workspace</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/dashboard.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/dashboard.log</string>
    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>
</dict>
</plist>
EOF

# Install plist
sudo mv /tmp/${PLIST_NAME}.plist "$PLIST_PATH"
sudo chown root:wheel "$PLIST_PATH"
sudo chmod 644 "$PLIST_PATH"

# Load the service
sudo launchctl load "$PLIST_PATH"

echo "✓ Service installed and started"
echo "  URL: http://localhost:8766"
echo "  Logs: ${LOG_DIR}/dashboard.log"
echo ""
echo "Commands:"
echo "  sudo launchctl stop ${PLIST_NAME}     # Stop"
echo "  sudo launchctl start ${PLIST_NAME}    # Start"
echo "  sudo launchctl unload ${PLIST_PATH}   # Uninstall"
