import configparser
import subprocess
import os
import logging
import socket
from pyroute2 import IPRoute, NDB, NetNS

logger = logging.getLogger(__name__)

def parse_config(config_path):
    """
    Parses a WireGuard config file (INI format).
    Returns a dict with 'Interface' and 'Peer' sections.
    Note: Standard WG configs can have multiple Peers, but for this prototype
    we'll focus on the first one or return a list.
    """
    config = configparser.ConfigParser()
    # WG configs often don't have spaces around =
    try:
        config.read(config_path)
    except Exception as e:
        logger.error(f"Failed to read config: {e}")
        raise

    return config

def setup_tunnel(config_path, ns_name="saferoute_ns", ifname="wg0"):
    """
    Sets up a WireGuard tunnel inside a network namespace.
    """
    config = parse_config(config_path)
    
    # Extract details
    if 'Interface' not in config:
        raise ValueError("Config missing [Interface] section")
    
    interface_conf = config['Interface']
    private_key = interface_conf.get('PrivateKey')
    address = interface_conf.get('Address') # e.g. 10.2.0.2/32
    dns = interface_conf.get('DNS')
    
    # We assume one peer for now
    peers_sections = [s for s in config.sections() if s == 'Peer']
    if not peers_sections:
        raise ValueError("Config missing [Peer] section")
        
    peer_conf = config[peers_sections[0]]
    public_key = peer_conf.get('PublicKey')
    endpoint = peer_conf.get('Endpoint') # e.g. 1.2.3.4:51820
    allowed_ips = peer_conf.get('AllowedIPs', '0.0.0.0/0')
    
    logger.info(f"Setting up tunnel from {config_path} in namespace {ns_name}")
    
    # 1. Create NetNS
    # Use subprocess 'ip netns' for robust creation in Docker
    netns_dir = '/var/run/netns'
    if not os.path.exists(netns_dir):
        os.makedirs(netns_dir)

    # Docker Workaround: ip netns requires /var/run/netns to be a shared mount point
    # We blindly attempt to fix this by bind mounting it to itself if it fails.
    try:
        # Check if we can create a dummy ns, if not, apply fix
        subprocess.check_output(["ip", "netns", "add", "test_mount_check"], stderr=subprocess.STDOUT)
        subprocess.run(["ip", "netns", "del", "test_mount_check"])
    except subprocess.CalledProcessError:
        logger.info("Applying Docker NetNS mount workaround...")
        # Bind mount directory to itself
        subprocess.run(["mount", "--bind", netns_dir, netns_dir])
        # Make it shared
        subprocess.run(["mount", "--make-shared", netns_dir])

    # Clean up old NS if exists
    subprocess.run(["ip", "netns", "del", ns_name], capture_output=True)
    
    # Create new NS
    # This creates the file in /var/run/netns and handles the bind mount
    proc = subprocess.run(["ip", "netns", "add", ns_name], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to create namespace {ns_name}: {proc.stderr.strip()}. (Did you run with --privileged?)")

    # 2. Create WG interface
    # We prefer creating it in the host then moving it to ensure we can see it
    ip = IPRoute()
    
    # Check if exists
    existing = ip.link_lookup(ifname=ifname)
    if existing:
        logger.info(f"Interface {ifname} exists, deleting to start fresh")
        ip.link('del', index=existing[0])
    
    logger.info(f"Creating WireGuard interface {ifname}")
    try:
        ip.link('add', ifname=ifname, kind='wireguard')
    except Exception as e:
        # Fallback: link might be stuck or specific error
        raise RuntimeError(f"Failed to create wireguard interface: {e}")
    
    # 3. Move to NetNS
    idx = ip.link_lookup(ifname=ifname)[0]
    logger.info(f"Moving {ifname} to namespace {ns_name}")
    ip.link('set', index=idx, net_ns_fd=ns_name)
    
    # Now interact with the interface INSIDE the namespace
    # Note: We need to close the host generic IPRoute and use the NS one
    ip.close()
    
    # Open the NS we just created
    with NetNS(ns_name) as ns_ip:
        idx = ns_ip.link_lookup(ifname=ifname)[0]
        
        # 4. Configure WireGuard Interface (Keys, Peers)
        # Use 'wg' CLI inside the namespace for reliability
        logger.info("Configuring WireGuard crypto and peers using wg tool")
        
        # Write private key to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tf:
            tf.write(private_key)
            pk_path = tf.name
            
        # Parse Endpoint and Resolve DNS (host side)
        # We must resolve here because the namespace has no internet access yet/at all (for DNS)
        # WireGuard "socket in original NS" handles the tunnel traffic, but 'wg set' needs an IP.
        ep_host, ep_port = endpoint.split(':')
        try:
            logger.info(f"Resolving endpoint: {ep_host}")
            ep_ip = socket.gethostbyname(ep_host)
            real_endpoint = f"{ep_ip}:{ep_port}"
            logger.info(f"Resolved to: {real_endpoint}")
        except Exception as e:
            logger.error(f"Failed to resolve endpoint {ep_host}: {e}")
            raise

        try:
            # Construct wg set command
            # ip netns exec <ns> wg set <iface> private-key <file> peer <pub> endpoint <ep> allowed-ips <ips>
            cmd = [
                "ip", "netns", "exec", ns_name,
                "wg", "set", ifname,
                "private-key", pk_path,
                "peer", public_key,
                "endpoint", real_endpoint,
                "allowed-ips", allowed_ips,
                "persistent-keepalive", "25"
            ]
            
            subprocess.run(cmd, check=True)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to configure WG: {e}")
            raise
        finally:
            if os.path.exists(pk_path):
                os.remove(pk_path)
        
        # 5. Bring IP up and assign address
        logger.info(f"Assigning address {address} and bringing up")
        ns_ip.link('set', index=idx, state='up')
        try:
            ns_ip.addr('add', index=idx, address=address)
        except Exception as e:
            logger.warning(f"Address assignment warning (might be dup): {e}")
        
        # 6. Set Routes
        # We want default traffic in this NS to go through WG
        # First we need to make sure loopback is up
        try:
            lo_idx = ns_ip.link_lookup(ifname='lo')[0]
            ns_ip.link('set', index=lo_idx, state='up')
        except IndexError:
            pass # No loopback?
        
        # Add default route
        # Note: WireGuard interfaces don't strictly need a gateway IP, just dev
        # But we must delete existing default if any? New NS shouldn't have one.
        logger.info("Adding default route")
        try:
            # use subprocess for reliability
            subprocess.run(["ip", "netns", "exec", ns_name, "ip", "route", "add", "default", "dev", ifname], check=True)
        except subprocess.CalledProcessError as e:
             logger.warning(f"Failed to add default route: {e}")

        # 7. Setup DNS for the namespace
        # 'ip netns exec' looks for /etc/netns/<name>/resolv.conf
        # If we don't set this, it uses the host's resolv.conf which usually points to Docker's
        # internal DNS (127.0.0.11), which is NOT reachable through the WG tunnel.
        if dns:
            logger.info(f"Configuring DNS: {dns}")
            netns_etc = '/etc/netns'
            if not os.path.exists(netns_etc):
                os.makedirs(netns_etc)
            
            resolv_path = os.path.join(netns_etc, ns_name, 'resolv.conf')
            # The directory /etc/netns/<ns_name> might not exist? 
            # Actually ip netns conventions: /etc/netns/<name>/resolv.conf
            # We need to create the subdir first.
            ns_etc_dir = os.path.join(netns_etc, ns_name)
            if not os.path.exists(ns_etc_dir):
                os.makedirs(ns_etc_dir)
                
            with open(os.path.join(ns_etc_dir, 'resolv.conf'), 'w') as f:
                for d in dns.replace(',', ' ').split():
                    f.write(f"nameserver {d}\n")
        else:
            logger.warning("No DNS configured! Connectivity check might fail if relying on host DNS.")

    logger.info("Tunnel setup complete.")
    return ns_name, ifname
