FROM python:3.9-slim

# Install only essential packages:
# - iptables: Required for NAT/masquerading rules
# - wireguard-tools: Provides 'wg' command for debugging
RUN apt-get update && apt-get install -y \
    iptables \
    wireguard-tools \
    iproute2 \
    openresolv \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and web app
COPY src/ ./src/
COPY app/ ./app/

# Expose web UI port
EXPOSE 8080

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Privileged mode required at runtime to modify network stack
# Default to running the web server
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "app.server"]
