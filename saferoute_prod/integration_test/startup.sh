#!/bin/bash
set -e

# Parse arguments
NO_CACHE=false
if [[ "$1" == "--no-cache" ]]; then
    NO_CACHE=true
fi

echo "🔨 Building saferoute_gateway image..."
if [ "$NO_CACHE" = true ]; then
    echo "   (Building with --no-cache)"
    docker-compose build --no-cache gateway
else
    echo "   (Using cache for faster builds)"
    docker-compose build gateway
fi

echo ""
echo "🚀 Starting containers..."
docker-compose up -d

echo ""
echo "✅ Startup complete!"
echo ""
echo "Containers running:"
docker-compose ps

echo ""
echo "📝 To run automatic setup:"
echo "   docker exec saferoute_gateway python -m src.app startup /app/data/configs/config.yaml"
echo ""
echo "💡 Tip: Use './startup.sh --no-cache' to rebuild without cache (e.g., after changing dependencies)"
