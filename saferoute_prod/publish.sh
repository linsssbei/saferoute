#!/bin/bash
set -e

# Configuration
IMAGE_NAME="ghcr.io/linsssbei/saferoute"
TAG="25"

echo "🐳 Building and Pushing for Multi-Arch (amd64 + arm64)..."

# Create a buildx builder if one doesn't exist
docker buildx version >/dev/null 2>&1 || { echo "❌ Docker Buildx not available"; exit 1; }
if ! docker buildx inspect saferoute-builder >/dev/null 2>&1; then
    docker buildx create --name saferoute-builder --use
fi

echo "� Building and Pushing..."
echo "Note: This requires you to be logged in (docker login ghcr.io)"
docker buildx build --platform linux/amd64,linux/arm64 -t $IMAGE_NAME:$TAG --push .

echo "✅ Done! Image pushed to $IMAGE_NAME:$TAG"
echo "You can now verify the manifest matches your QNAP architecture."

