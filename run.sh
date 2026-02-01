#!/bin/bash
set -e

# Build the image ensuring it's up to date
echo "Building Docker image..."
docker build -t saferoute .

# Run with privileged flag ensuring network operations verify
echo "Running Saferoute..."
# We forward all arguments to the container entrypoint
docker run -it --rm --privileged \
  -v "$(pwd)/example.conf:/app/wg.conf" \
  saferoute "$@"
