FROM python:3.11-slim

# Install system dependencies for networking
RUN apt-get update && apt-get install -y \
    iproute2 \
    wireguard-tools \
    iputils-ping \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/run/netns

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY saferoute ./saferoute

# Install dependencies and the package itself
# We use pip to install from the current directory
RUN pip install --no-cache-dir .

# Set entrypoint so we can just run "connect" args
ENTRYPOINT ["saferoute"]
CMD ["--help"]
