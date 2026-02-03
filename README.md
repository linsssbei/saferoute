# Saferoute

**Smart VPN Routing Gateway for Home Labs & NAS**

Saferoute is a lightweight, Docker-based gateway that allows you to route specific devices on your home network through WireGuard VPN tunnels, while letting others bypass the VPN entirely. 

It is designed to solve the "all-or-nothing" problem of router-based VPNs. With Saferoute, you can unblock streaming content on your TV (via a VPN) while keeping your gaming PC or work laptop on your fast, local ISP connection—all controlled via a simple Web UI.

![Dashboard Screenshot](https://raw.githubusercontent.com/linsssbei/saferoute/main/docs/dashboard.png)

---

## 🚀 Why Saferoute?

-   **Per-Device Routing**: Assign specific LAN devices (by IP) to specific VPN tunnels.
-   **WireGuard Support**: Native WireGuard implementation for high performance.
-   **Web Management UI**: Easily upload configs, toggle mappings, and view status.
-   **NAS Friendly**: Optimized for QNAP/Synology (Docker) with host networking support.
-   **Performance Optimized**: Includes automatic **TCP MSS Clamping** to prevent fragmentation and slow speeds typical of VPNs.
-   **Resilient**: Automatically cleans up stale interfaces and generates default configs on startup.

---

## 🛠️ Installation

### Prerequisites
-   A device running Docker (NAS, Raspberry Pi, Linux Server).
-   A WireGuard configuration file (`.conf`) from your VPN provider (e.g., Surfshark, NordVPN, Mullvad).

### 1. Docker Compose (Recommended)

Create a `docker-compose.yaml` file:

```yaml
services:
  saferoute:
    image: ghcr.io/linsssbei/saferoute:latest
    container_name: saferoute_gateway
    restart: unless-stopped
    privileged: true
    network_mode: host  # CRITICAL for routing LAN traffic
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    environment:
      - CONFIG_DIR=/app/data/configs
      - TZ=UTC
      - PORT=8080 # Web UI Port (Change if 8080 is taken)
    volumes:
      - ./data:/app/data/configs
      - /lib/modules:/lib/modules # Required for kernel modules
```

### 2. Run the Container

```bash
docker-compose up -d
```

### 3. Access the UI
Open your browser and navigate to:
`http://<YOUR-DEVICE-IP>:8080`

---

## ⚙️ Configuration Guide

### Step 1: Add a WireGuard Tunnel
1.  Go to the **WireGuard Configs** tab in the UI.
2.  Click **Upload Config** and select your `.conf` file.
    -   *Tip: Ensure your config has the correct `Endpoint` IP and keys.*
3.  The tunnel will appear in the dashboard.

### Step 2: Configure Your Client Device (CRITICAL)
To route a device (e.g., Apple TV, Phone, PC) through Saferoute, you must change its network settings manually.

On the client device:
1.  **IP Address**: Set a Static IP (e.g., `192.168.0.123`).
2.  **Subnet Mask**: Default (usually `255.255.255.0`).
3.  **Router / Gateway**: Set to **Saferoute's Host IP** (e.g., `192.168.0.100`).
4.  **DNS**: **DO NOT** use your router's IP. Use a Public DNS.
    -   Primary: `1.1.1.1` (Cloudflare) or `8.8.8.8` (Google)
    -   Secondary: `1.0.0.1` or `8.8.4.4`

> **Note**: Setting the DNS to a public provider is required for Geo-Unblocking to work correctly. If you use your local router's DNS, traffic may leak or resolve to local CDN servers.

### Step 3: Map Device to Tunnel
1.  Go to the **Mappings** tab in the UI.
2.  Click **Add Mapping**.
3.  Enter your client's IP (e.g., `192.168.0.123`).
4.  Select the Tunnel you uploaded (e.g., `tw` for Taiwan).
5.  Toggle **Active** to ON.
6.  Click **Apply All**.

🎉 **Done!** That specific device is now browsing through Taiwan, while the rest of your home network stays local.

---

## 🔧 Troubleshooting

### "Netflix/Streaming is still slow or not loading"
This is usually a **DNS Issue**.
-   Ensure your client device is NOT using your router's IP for DNS.
-   Set client DNS to `8.8.8.8` (Google) or the DNS recommended by your VPN provider.
-   Flush your DNS cache or restart the client device.

### "I deleted the container and my tunnels are gone but still running"
We fixed this! Saferoute now automatically detects and cleans up stale `sr_*` interfaces on startup. Just restart the container.

### "Port 8080 is already in use"
Change the `PORT` environment variable in your `docker-compose.yaml`:
```yaml
environment:
  - PORT=9696
```
Then access at `http://<IP>:9696`.

---

## 🏗️ Architecture via QNAP/Docker

Saferoute uses **Policy Based Routing (PBR)** on Linux:
1.  It creates a dedicated routing table for each VPN tunnel.
2.  It uses `iptables` and `ip rule` to mark traffic coming from specific Source IPs.
3.  Marked traffic is forced into the specific VPN table.
4.  **Masquerading (NAT)** is applied so traffic returns correctly.
5.  **TCP MSS Clamping** is applied to ensure packet headers fit inside the VPN tunnel, preventing huge speed drops.
