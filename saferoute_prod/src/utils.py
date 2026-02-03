import logging
import subprocess
import os

def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def get_env_var(name, default=None):
    return os.environ.get(name, default)

def enable_ipv4_forwarding():
    """
    Equivalent to sysctl -w net.ipv4.ip_forward=1
    """
    try:
        with open('/proc/sys/net/ipv4/ip_forward', 'w') as f:
            f.write('1')
    except Exception as e:
        logging.getLogger('utils').error(f"Failed to enable ip_forward: {e}")

def enable_src_valid_mark():
    """
    Equivalent to sysctl -w net.ipv4.conf.all.src_valid_mark=1
    Required for WireGuard routing with fwmark.
    """
    try:
        with open('/proc/sys/net/ipv4/conf/all/src_valid_mark', 'w') as f:
            f.write('1')
    except Exception as e:
        logging.getLogger('utils').error(f"Failed to enable src_valid_mark: {e}")

def enable_masquerade():
    """
    Still using iptables subprocess for NAT as pyroute2/nftables is complex
    and usually requires 'iptables' binary or 'nft' binary present.
    Pure python nftables is possible but external dependency (nftables-python).
    We stick to subprocess for this one command for now as agreed refactor was mainly for 'ip' commands.
    """
    try:
        subprocess.run(["iptables", "-t", "nat", "-A", "POSTROUTING", "-o", "eth0", "-j", "MASQUERADE"], check=False)
        subprocess.run(["iptables", "-t", "nat", "-A", "POSTROUTING", "-o", "wg_+", "-j", "MASQUERADE"], check=False)
    except Exception:
        pass
