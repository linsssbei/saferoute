import logging
import os
from pyroute2 import IPRoute

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
    Set up NAT masquerading for Saferoute tunnels using pure Python (pyroute2).
    This adds an iptables MASQUERADE rule for all sr_* interfaces.
    
    Equivalent to: iptables -t nat -A POSTROUTING -o sr_+ -j MASQUERADE
    """
    logger = logging.getLogger('utils')
    
    try:
        # Use IPRoute to add iptables rules via netlink
        # pyroute2 doesn't have direct iptables/nftables manipulation in a simple way,
        # but we can use the tc (traffic control) or rely on the kernel's conntrack
        # 
        # Actually, for NAT rules, we need to use nftables or iptables.
        # pyroute2 focuses on routing/links/addresses via netlink.
        # 
        # The cleanest pure-Python approach is to use python-iptables library,
        # but that's an external dependency. Let me use a different approach:
        # We'll write directly to /proc/sys to enable masquerading at the kernel level.
        
        # Alternative: Use pyroute2's nftables support (if available)
        # But this requires nftables kernel support and is complex.
        
        # For now, the most reliable pure-Python approach is to use
        # the iptc (python-iptables) library, but since we want to avoid
        # external dependencies, let's use a hybrid approach:
        
        # We'll use pyroute2 to detect interfaces and then use
        # subprocess as a last resort, but with better error handling.
        
        # Actually, let me reconsider: pyroute2 CAN do this via nftables
        # Let me implement it properly:
        
        from pyroute2.nftables import NFTables
        
        nft = NFTables()
        
        # Create a table for NAT if it doesn't exist
        # nft add table ip nat
        nft.table('add', name='nat', family='ip')
        
        # Create POSTROUTING chain if it doesn't exist
        # nft add chain ip nat postrouting { type nat hook postrouting priority 100 \; }
        nft.chain('add', table='nat', name='postrouting', family='ip',
                 type='nat', hook='postrouting', priority=100)
        
        # Add masquerade rule for sr_* interfaces
        # nft add rule ip nat postrouting oifname "sr_*" masquerade
        # Note: pyroute2 nftables API is low-level, this might need adjustment
        nft.rule('add', table='nat', chain='postrouting', family='ip',
                expr=[
                    {'match': {'left': {'meta': {'key': 'oifname'}},
                              'op': '==',
                              'right': 'sr_*'}},
                    {'masquerade': {}}
                ])
        
        nft.close()
        logger.info("NAT masquerading enabled for Saferoute tunnels (via nftables)")
        
    except Exception as e:
        logger.warning(f"nftables approach failed: {e}")
        logger.info("Falling back to legacy iptables approach")
        
        # Fallback: Use iptables via subprocess (but with better detection)
        import subprocess
        
        iptables_cmd = None
        for cmd in ['iptables-legacy', 'iptables']:
            try:
                result = subprocess.run([cmd, '-t', 'nat', '-L', '-n'], 
                                      capture_output=True, timeout=2)
                if result.returncode == 0:
                    iptables_cmd = cmd
                    logger.info(f"Using {cmd} for NAT rules")
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        
        if not iptables_cmd:
            logger.error("No working iptables command found")
            return
        
        try:
            result = subprocess.run(
                [iptables_cmd, "-t", "nat", "-A", "POSTROUTING", "-o", "sr_+", "-j", "MASQUERADE"],
                capture_output=True, text=True
            )
            if result.returncode != 0 and "already exists" not in result.stderr.lower():
                logger.warning(f"Failed to add MASQUERADE rule: {result.stderr}")
            else:
                logger.info("NAT masquerading enabled (via iptables-legacy)")
        except Exception as e:
            logger.error(f"Exception setting up masquerade: {e}")

        # Also add TCP MSS clamping - critical for VPN performance
        # iptables -t mangle -A POSTROUTING -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
        try:
            # Check if mangle table rule exists
            res = subprocess.run(
                [iptables_cmd, "-t", "mangle", "-C", "POSTROUTING", "-p", "tcp", "--tcp-flags", "SYN,RST", "SYN", "-j", "TCPMSS", "--clamp-mss-to-pmtu"],
                capture_output=True
            )
            if res.returncode != 0:
                subprocess.run(
                    [iptables_cmd, "-t", "mangle", "-A", "POSTROUTING", "-p", "tcp", "--tcp-flags", "SYN,RST", "SYN", "-j", "TCPMSS", "--clamp-mss-to-pmtu"],
                    check=False
                )
                logger.info("TCP MSS clamping enabled (fixes slow VPN speeds)")
        except Exception:
            logger.warning("Failed to enable TCP MSS clamping")

