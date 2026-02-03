#!/bin/bash
set -e

# Directories
CONFIG_DIR="./configs/wireguard"
SERVER_CONFIG_DIR="./configs/server"

# Ensure directories exist
mkdir -p "$CONFIG_DIR"
mkdir -p "$SERVER_CONFIG_DIR"

echo "Generating WireGuard keys..."

# 1. Generate Keys for Gateway (Client)
GATEWAY_PRIV=$(docker run --rm --entrypoint wg lscr.io/linuxserver/wireguard:latest genkey)
GATEWAY_PUB=$(echo "$GATEWAY_PRIV" | docker run --rm -i --entrypoint wg lscr.io/linuxserver/wireguard:latest pubkey)

# 2. Generate Keys for Mock Server
SERVER_PRIV=$(docker run --rm --entrypoint wg lscr.io/linuxserver/wireguard:latest genkey)
SERVER_PUB=$(echo "$SERVER_PRIV" | docker run --rm -i --entrypoint wg lscr.io/linuxserver/wireguard:latest pubkey)

echo "Gateway Public Key: $GATEWAY_PUB"
echo "Server Public Key:  $SERVER_PUB"

# 3. Create Gateway Config (to be imported by saferoute)
# Connects to the mock server at 172.29.0.5:51820
cat > "$CONFIG_DIR/test-vpn.conf" <<EOF
[Interface]
PrivateKey = $GATEWAY_PRIV
Address = 10.13.13.2/32
DNS = 1.1.1.1

[Peer]
PublicKey = $SERVER_PUB
Endpoint = 172.30.0.5:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF

# 4. Create Mock Server Config
# Server running at 172.30.0.5 inside the docker network
cat > "$SERVER_CONFIG_DIR/wg0.conf" <<EOF
[Interface]
Address = 10.13.13.1/24
ListenPort = 51820
PrivateKey = $SERVER_PRIV

[Peer]
# Gateway Peer
PublicKey = $GATEWAY_PUB
AllowedIPs = 10.13.13.2/32
EOF

echo "✅ Test configurations generated:"
echo "   - $CONFIG_DIR/test-vpn.conf"
echo "   - $SERVER_CONFIG_DIR/wg0.conf"
echo ""
echo "You can now run 'docker-compose up -d' to start the test environment."
