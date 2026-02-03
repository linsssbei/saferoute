#!/bin/bash
set -e

CONFIG_DIR="${CONFIG_DIR:-/app/data/configs}"
CONFIG_FILE="$CONFIG_DIR/config.yaml"
MAPPINGS_DIR="$CONFIG_DIR/mappings"
WG_DIR="$CONFIG_DIR/wireguard"

# Ensure directories exist
mkdir -p "$MAPPINGS_DIR"
mkdir -p "$WG_DIR"

# Create default config.yaml if missing
if [ ! -f "$CONFIG_FILE" ]; then
    echo "📄 Generating default config.yaml..."
    cat > "$CONFIG_FILE" <<EOF
# Saferoute Default Configuration
wireguard_configs: $WG_DIR
device_mappings: $MAPPINGS_DIR/devices.yaml
EOF
fi

# Create empty devices.yaml if missing to prevent errors
if [ ! -f "$MAPPINGS_DIR/devices.yaml" ]; then
    echo "📄 Generating empty devices.yaml..."
    echo "devices: []" > "$MAPPINGS_DIR/devices.yaml"
fi

# Execute the CMD (start the app)
exec "$@"
